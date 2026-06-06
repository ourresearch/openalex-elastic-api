"""Flask Blueprint for the **translation** resource (`/query`) + the property catalog.

This module is PURE TRANSLATION and metadata — it NEVER touches Elasticsearch:

    GET /query/{oxurl|oql|oqo}/<q>  -> {oxurl, oql, oql_render, oqo, validation}
    GET /properties[/<entity>]      -> the entity-property catalog (+ /registry alias)

Each `/query/<fmt>/<q>` route parses the query from one representation and renders
it into all of them; it validates but does not execute.

**Execution** (which DOES hit ES) lives elsewhere: the engine is in
`query_translation/execution.py` and is exposed at the application root by
`works/views.py` (`GET /?oql=`, `GET /?oqo=`, `POST /`). It was split out of this
file (oxjob #384) precisely so the translation resource no longer cohabits with the
ES-executing machinery. If you came here looking for where `/query` "runs" a query:
it doesn't — see `execution.py`.
"""

import json
import time
import urllib.parse
import concurrent.futures
from collections import OrderedDict

import requests
from elasticsearch_dsl import Search
from flask import Blueprint, jsonify, request
from openai import OpenAI

import settings
from core.cursor import handle_cursor
from core.exceptions import APIError, APIQueryParamsError
from core.paginate import get_pagination, get_per_page
from core.shared_view import (
    apply_grouping, apply_sorting, execute_search, format_response, set_source, )
from core.preference import clean_preference, combine_preferences
from core.properties import get_entity_properties, render_properties
from core.utils import get_data_version_connection
from core.utils import get_display_name as _get_display_name
from query_translation.oqo import OQO, VALID_OPERATORS, filter_from_dict
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oqo_to_es import (
    OQOTranslationError, oqo_to_search_and_filter_q, )
from query_translation.oql_parser import OQLParseError, parse_oql_to_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.oql_tree_renderer import render_oqo_to_oql_and_tree
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import (
    URLRenderError, can_render_to_url, render_oqo_to_url, )
from query_translation.validator import (
    ValidationError, ValidationResult, validate_oqo, _has_search_clause, )


# Entity types that exist in Elasticsearch and can be looked up
NATIVE_ENTITY_TYPES = {
    "institutions", "authors", "sources", "publishers", "funders", "topics", "subfields", "fields", "domains", "keywords", "concepts"
}


def safe_get_display_name(entity_id: str):
    """
    Resolve entity display name from Elasticsearch for native entity types.

    Only queries Elasticsearch for entities that actually exist there.
    Non-native types (types, languages, countries, etc.) return None
    and are handled by the renderer's built-in lookup tables.

    The entity_id comes in as "institutions/i33213144" but get_display_name
    expects just the short ID "i33213144" (it prepends https://openalex.org/).
    """
    if not entity_id or "/" not in entity_id:
        return None

    entity_type, short_id = entity_id.split("/", 1)
    if entity_type not in NATIVE_ENTITY_TYPES:
        return None  # Let default resolver handle it

    try:
        # Pass just the short ID - get_display_name prepends the URL
        return _get_display_name(short_id)
    except Exception:
        return None


blueprint = Blueprint("query_translation", __name__)


# ---------------------------------------------------------------------------
# /properties — the entity-property catalog (#331; formerly #294's /registry)
#
# Every queryable property per entity, with its value type, valid filter
# operators, actions (filter/sort/select/group_by), and cross-type entity_type.
# Built at boot from the live `Field` objects the filter layer executes
# (core/properties.py), so it can't drift from what the server actually accepts.
# This is the same data the OQO validator consults to answer "is column X valid
# on entity Y with operator Z and value type T?".
#
# The payload is canonical (fully sorted) and carries `meta.version` +
# `meta.fingerprint`; `docs/properties-snapshot.json` is its committed mirror.
# `/registry*` remain as deprecated aliases (identical payload + `Deprecation`
# header) through a deprecation window.
#
# Per-entity form is `/properties/<entity>`, NOT `/entities/<entity>/properties`:
# the latter collides with the universal entity-by-id route
# `/entities/<entity>/<path:id>` (the `<path:id>` converter swallows "properties"
# as an id → 404). `/properties/<entity>` is an unambiguous sub-resource of the
# collection and matches the `?entity=` slice byte-for-byte.
# ---------------------------------------------------------------------------


def _deprecated(response):
    """Tag a response as a deprecated `/registry*` alias (RFC 8594)."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</properties>; rel="successor-version"'
    return response


def _properties_payload(entity_type):
    """Render the canonical payload for the full catalog (`entity_type=None`) or
    one entity, or an error tuple if the entity is unknown. Shared by the
    `/properties` routes and the deprecated `/registry*` aliases so they serve
    byte-identical bodies."""
    if entity_type is not None and get_entity_properties(entity_type) is None:
        return _error_response(
            f"'{entity_type}' is not a known entity type.", "invalid_entity", status=404, )
    return jsonify(render_properties(entity=entity_type)), 200


@blueprint.route("/properties", methods=["GET"])
def get_properties():
    """The full entity-property catalog, or one entity via `?entity=works`.

    `?entity=` returns the same body as `/properties/<entity>`.
    """
    return _properties_payload(request.args.get("entity"))


@blueprint.route("/properties/<entity_type>", methods=["GET"])
def get_entity_properties_route(entity_type: str):
    """The property catalog for a single entity type, e.g. `/properties/works`."""
    return _properties_payload(entity_type)


@blueprint.route("/registry", methods=["GET"])
def get_registry():
    """DEPRECATED alias of `/properties` (`?entity=` supported). Identical body;
    carries a `Deprecation` header. Use `/properties`."""
    payload, status = _properties_payload(request.args.get("entity"))
    if status != 200:
        return payload, status
    return _deprecated(payload), status


@blueprint.route("/registry/<entity_type>", methods=["GET"])
def get_registry_entity(entity_type: str):
    """DEPRECATED alias of `/properties/<entity_type>`. Identical body;
    carries a `Deprecation` header."""
    payload, status = _properties_payload(entity_type)
    if status != 200:
        return payload, status
    return _deprecated(payload), status


def _error_response(message, error_type, status=400):
    return jsonify(
        {
            "validation": {
                "valid": False, "errors": [
                    {"type": error_type, "message": message, "location": None}
                ], "warnings": [], }
        }
    ), status


# ---------------------------------------------------------------------------
# Translation resource: `/query` addressed by any one representation, returns
# all of them — {oxurl, oql, oql_render, oqo, validation}. The entity type is
# embedded in every format, so no entity_type param is needed.
#
#   GET /query/oxurl/:query   (e.g. /query/oxurl/works?filter=type:article)
#   GET /query/oql/:query
#   GET /query/oqo/:query
#
# :query is accepted both un-encoded (default, readable) and urlencoded.
# ---------------------------------------------------------------------------


@blueprint.route("/query", methods=["GET"])
def get_query():
    """Descriptor for the translation resource (no segment given)."""
    return jsonify(
        {
            "msg": (
                "Translate a query: GET /query/{oxurl|oql|oqo}/<query> "
                "(un-encoded or urlencoded) → {oxurl, oql, oql_render, oqo, "
                "validation}. Execute a query: GET /works?filter=…, "
                "GET /?oql=…, GET /?oqo=…, or POST / with {oqo} or {oql}."
            ), "documentation_url": "/docs", }
    ), 200


def _full_query_value(path_value: str) -> str:
    """Reconstruct the full query string from the `<path:value>` segment plus
    the real querystring, so both encodings work:

    - raw:     GET /query/oxurl/works?filter=type:article
               → path_value="works", query_string="filter=type:article"
    - encoded: GET /query/oxurl/works%3Ffilter%3Dtype%3Aarticle
               → path_value="works?filter=type:article", no query_string
    """
    qs = request.query_string.decode("utf-8")
    if qs and "?" not in path_value:
        return f"{path_value}?{qs}"
    return path_value


def _parse_oxurl_value(value: str):
    """Parse an oxurl string (`works?filter=…&sort=…`) into an OQO.

    Returns (oqo, error_string). `search.<field>=` params are folded into the
    filter string as `<field>.search:<value>` (the OQO's representation of a
    scoped free-text search); a bare `search=` is passed through.
    """
    value = value.lstrip("/")
    if "?" in value:
        entity_type, qs = value.split("?", 1)
    else:
        entity_type, qs = value, ""
    entity_type = entity_type.strip().strip("/")

    params = {}
    for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True):
        params[k] = v

    # Fold scoped search params (search.title_and_abstract=…) into filter clauses.
    extra_filters = []
    for k, v in list(params.items()):
        if k.startswith("search.") and v:
            field = k[len("search."):]
            extra_filters.append(f"{field}.search:{v}")
    if extra_filters:
        base = params.get("filter")
        params["filter"] = ", ".join(([base] if base else []) + extra_filters)

    input_data = {
        "filter": params.get("filter"), "sort": params.get("sort"), "search": params.get("search"), "group_by": params.get("group_by"), "select": params.get("select"), "sample": params.get("sample"), "seed": params.get("seed"), "per_page": params.get("per_page") or params.get("per-page"), "page": params.get("page"), "cursor": params.get("cursor"), }
    return parse_url_input(entity_type, input_data)


def _translate_response(oqo, parse_error):
    """Shared tail for the translation routes: validate + render all formats."""
    if parse_error:
        return _error_response(parse_error, "parse_error", status=400)

    validation_result = validate_oqo(oqo)
    if not validation_result.valid:
        return jsonify({
            "oxurl": None, "oql": None, "oqo": oqo.to_dict(), "validation": validation_result.to_dict(), }), 400

    return jsonify(render_all_formats(oqo, validation_result)), 200


@blueprint.route("/query/oxurl/<path:value>", methods=["GET"])
def translate_oxurl(value: str):
    """Translate an OpenAlex URL (`works?filter=…`) to all formats.

    Translation only — parses + renders {oxurl, oql, oql_render, oqo, validation};
    does NOT execute the query or touch ES. Execution lives at the root — see
    `query_translation/execution.py`.
    """
    oqo, err = _parse_oxurl_value(_full_query_value(value))
    return _translate_response(oqo, err)


@blueprint.route("/query/oql/<path:value>", methods=["GET"])
def translate_oql(value: str):
    """Translate an OQL string to all formats (no execution / no ES)."""
    oql = _full_query_value(value)
    try:
        oqo = parse_oql_to_oqo(oql)
    except Exception as e:  # OQLParseError and friends → 400
        return _error_response(f"Failed to parse OQL: {e}", "parse_error", status=400)
    return _translate_response(oqo, None)


@blueprint.route("/query/oqo/<path:value>", methods=["GET"])
def translate_oqo(value: str):
    """Translate an OQO (URL-encoded or raw JSON) to all formats (no execution / no ES)."""
    oqo, err = parse_oqo_input(None, _full_query_value(value))
    return _translate_response(oqo, err)


def parse_url_input(entity_type: str, input_data):
    """Parse URL format input."""
    try:
        if isinstance(input_data, dict):
            # Input is already structured: {"filter": "...", "sort": "...", "group_by": "..."}
            filter_string = input_data.get("filter")
            sort_string = input_data.get("sort")
            sample = input_data.get("sample")
            group_by_string = input_data.get("group_by")
            select_string = input_data.get("select")
            seed = input_data.get("seed")
            per_page = input_data.get("per_page") or input_data.get("per-page")
            page = input_data.get("page")
            cursor = input_data.get("cursor")
            search_string = input_data.get("search")
        else:
            # Input is just the filter string
            filter_string = input_data
            sort_string = None
            sample = None
            group_by_string = None
            select_string = None
            seed = None
            per_page = None
            page = None
            cursor = None
            search_string = None

        oqo = parse_url_to_oqo(
            entity_type=entity_type, filter_string=filter_string, sort_string=sort_string, sample=sample, group_by_string=group_by_string, select_string=select_string, seed=seed, per_page=per_page, page=page, cursor=cursor, search_string=search_string, )
        return oqo, None
    except Exception as e:
        return None, f"Failed to parse URL format: {str(e)}"


def parse_oqo_input(entity_type: str, input_data):
    """Parse OQO format input."""
    try:
        if isinstance(input_data, str):
            import json
            input_data = json.loads(input_data)
        
        # Ensure entity_type matches
        if "get_rows" not in input_data:
            input_data["get_rows"] = entity_type
        
        oqo = OQO.from_dict(input_data)
        return oqo, None
    except Exception as e:
        return None, f"Failed to parse OQO format: {str(e)}"


# oxurl component order — the readable order the GUI/users emit. `search` is
# folded into `filter` as a `default.search:` clause by render_oqo_to_url, so it
# is not a separate key here.
_OXURL_COMPONENT_ORDER = (
    "filter", "sort", "group_by", "select", "sample", "seed", "per_page", "page", "cursor", )


def _components_to_oxurl(entity_type: str, components: dict) -> str:
    """Build a readable OpenAlex URL string (e.g. `/works?filter=type:article`)
    from the entity type + the component dict returned by render_oqo_to_url.

    `:` `, ` `|` are left un-encoded (readable filter syntax); spaces and other
    reserved chars are percent-encoded so the URL is still valid.
    """
    pairs = []
    for key in _OXURL_COMPONENT_ORDER:
        value = components.get(key)
        if value is None or value == "":
            continue
        pairs.append(f"{key}={urllib.parse.quote(str(value), safe=':, |')}")
    base = f"/{entity_type}"
    return base + ("?" + "&".join(pairs) if pairs else "")


def render_all_formats(oqo: OQO, validation_result: ValidationResult):
    """Render OQO to all output formats: {oxurl, oql, oql_render, oqo, validation}."""
    warnings = list(validation_result.warnings)

    # Canonicalize OQO for deterministic output
    canonical_oqo = canonicalize_oqo(oqo)

    # Render to oxurl (OpenAlex URL string)
    oxurl_output = None
    try:
        components = render_oqo_to_url(canonical_oqo)
        oxurl_output = _components_to_oxurl(canonical_oqo.get_rows, components)
    except URLRenderError as e:
        warnings.append(ValidationError(
            type="url_not_representable", message=str(e)
        ))

    # Render to OQL and oql_render tree
    # Pass safe_get_display_name as entity resolver to include display names in oql_render
    oql_output, oql_render_tree = render_oqo_to_oql_and_tree(
        canonical_oqo, entity_resolver=safe_get_display_name
    )

    # Build response
    return {
        "oxurl": oxurl_output, "oql": oql_output, "oql_render": oql_render_tree.to_dict(), "oqo": canonical_oqo.to_dict(), "validation": {
            "valid": True, "errors": [
                {"type": e.type, "message": e.message, "location": e.location}
                for e in validation_result.errors
            ], "warnings": [
                {"type": w.type, "message": w.message, "location": w.location}
                for w in warnings
            ]
        }
    }


OPENAI_MODEL = "gpt-5"
OPENAI_PROMPT_ID = "pmpt_69549fae727481958ec7aaa4ee976b5a06d01a66a3e9b225"

# Shared config for API calls - matches stored prompt settings
TEXT_CONFIG = {
    "format": {
        "type": "json_schema", "name": "OpenAlex_Query_Object", "strict": False, "schema": {
            "type": "object", "properties": {}, "required": []
        }
    }, "verbosity": "low"
}

REASONING_CONFIG = {"summary": "auto"}


@blueprint.route("/query/natural-language/<path:natural_language_query>", methods=["GET"])
def get_natural_language_query(natural_language_query: str):
    """
    Convert a natural language query to OQO using OpenAI, then return all formats.

    URL path param:
    - natural_language_query: Natural language description of the query

    Response: Same format as /query endpoint, plus meta.timing information
    """
    return jsonify({"error": "Not found"}), 404

    # try:
    #     oqo_dict, timing_meta = convert_natural_language_to_oqo(natural_language_query)
    #
    #     # Check for error response from model
    #     if "error" in oqo_dict:
    #         return jsonify({"msg": oqo_dict["error"], "meta": {"timing": timing_meta}}), 400
    #
    #     # Parse the OQO
    #     entity_type = oqo_dict.get("get_rows", "works")
    #     oqo, parse_error = parse_oqo_input(entity_type, oqo_dict)
    #
    #     if parse_error:
    #         return jsonify({
    #             "url": None, #             "oql": None, #             "oqo": None, #             "validation": {
    #                 "valid": False, #                 "errors": [{"type": "parse_error", "message": parse_error}], #                 "warnings": []
    #             }
    #         }), 400
    #
    #     validation_result = validate_oqo(oqo)
    #
    #     if not validation_result.valid:
    #         return jsonify({
    #             "url": None, #             "oql": None, #             "oqo": oqo.to_dict(), #             "validation": validation_result.to_dict()
    #         }), 400
    #
    #     response = render_all_formats(oqo, validation_result)
    #     response["meta"] = {"timing": timing_meta}
    #     return jsonify(response), 200
    #
    # except Exception as e:
    #     return jsonify({
    #         "url": None, #         "oql": None, #         "oqo": None, #         "validation": {
    #             "valid": False, #             "errors": [{"type": "internal_error", "message": str(e)}], #             "warnings": []
    #         }
    #     }), 500


def convert_natural_language_to_oqo(natural_language_query: str) -> tuple[dict, dict]:
    """
    Use OpenAI to convert natural language to OQO format.
    Uses stored prompt with variables and handles tool calls for entity resolution.
    
    Returns:
        tuple: (oqo_dict, timing_meta)
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Timing tracking
    timing = {
        "openai_calls": [], "tool_calls": [], }
    total_start = time.time()
    
    # Initial call with stored prompt and variables
    openai_start = time.time()
    response = client.responses.create(
        model=OPENAI_MODEL, prompt={
            "id": OPENAI_PROMPT_ID, "variables": {
                "query": natural_language_query
            }
        }, input=[], text=TEXT_CONFIG, reasoning=REASONING_CONFIG, store=True
    )
    openai_elapsed = time.time() - openai_start
    timing["openai_calls"].append({
        "call_number": 1, "duration_ms": round(openai_elapsed * 1000, 1), "had_tool_calls": any(item.type == "function_call" for item in response.output)
    })
    
    # Process tool calls in a loop until we get a final response
    max_iterations = 5
    iteration = 0
    while response.output and any(item.type == "function_call" for item in response.output):
        iteration += 1
        if iteration > max_iterations:
            return {"error": "Too many tool call iterations"}, timing
        
        tool_calls = [item for item in response.output if item.type == "function_call"]
        
        # Build follow-up input: previous output items + tool call outputs
        follow_up_input = []
        
        # Add all items from previous response output
        for item in response.output:
            if item.type == "reasoning":
                follow_up_input.append({
                    "type": "reasoning", "id": item.id, "summary": [{"type": "summary_text", "text": s.text} for s in (item.summary or [])], "encrypted_content": getattr(item, 'encrypted_content', '')
                })
            elif item.type == "function_call":
                follow_up_input.append({
                    "type": "function_call", "id": item.id, "call_id": item.call_id, "name": item.name, "arguments": item.arguments
                })
        
        # Execute tool calls in parallel and add outputs
        tool_start = time.time()
        tool_results = execute_tool_calls_parallel(tool_calls)
        tool_elapsed = time.time() - tool_start
        
        tool_call_info = {
            "iteration": iteration, "num_calls": len(tool_calls), "duration_ms": round(tool_elapsed * 1000, 1), "calls": [
                {
                    "entity_type": json.loads(tc.arguments).get("entity_type"), "query": json.loads(tc.arguments).get("query")
                }
                for tc in tool_calls
            ]
        }
        timing["tool_calls"].append(tool_call_info)
        
        for tool_call, result in zip(tool_calls, tool_results):
            follow_up_input.append({
                "type": "function_call_output", "call_id": tool_call.call_id, "output": json.dumps(result)
            })
        
        # Make follow-up call with full conversation
        openai_start = time.time()
        response = client.responses.create(
            model=OPENAI_MODEL, prompt={
                "id": OPENAI_PROMPT_ID, "variables": {
                    "query": natural_language_query
                }
            }, input=follow_up_input, text=TEXT_CONFIG, reasoning=REASONING_CONFIG, store=True
        )
        openai_elapsed = time.time() - openai_start
        timing["openai_calls"].append({
            "call_number": len(timing["openai_calls"]) + 1, "duration_ms": round(openai_elapsed * 1000, 1), "had_tool_calls": any(item.type == "function_call" for item in response.output)
        })
    
    # Calculate totals
    timing["total_openai_ms"] = round(sum(c["duration_ms"] for c in timing["openai_calls"]), 1)
    timing["total_tool_calls_ms"] = round(sum(c["duration_ms"] for c in timing["tool_calls"]), 1)
    timing["total_elapsed_ms"] = round((time.time() - total_start) * 1000, 1)
    timing["num_openai_calls"] = len(timing["openai_calls"])
    timing["num_tool_call_rounds"] = len(timing["tool_calls"])
    
    # Extract the final text response containing OQO JSON
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    return json.loads(content.text), timing
    
    return {"error": "No valid response from model"}, timing


def execute_tool_calls_parallel(tool_calls: list) -> list:
    """Execute multiple tool calls in parallel and return results in order."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(execute_resolve_entity, tool_call)
            for tool_call in tool_calls
        ]
        return [future.result() for future in futures]


def normalize_openalex_id(full_id: str) -> str:
    """
    Convert full OpenAlex ID URL to short format.
    
    Example: https://openalex.org/A5023888391 -> a5023888391
    """
    if not full_id:
        return full_id
    # Extract the ID part after the last slash and lowercase it
    short_id = full_id.split("/")[-1].lower()
    return short_id


def execute_resolve_entity(tool_call) -> dict:
    """
    Execute a resolve_entity tool call by hitting the OpenAlex API.
    Returns the single best matching ID: {"id": "i123456"}
    """
    args = json.loads(tool_call.arguments)
    entity_type = args.get("entity_type", "works")
    query = args.get("query", "")
    
    url = f"https://api.openalex.org/{entity_type}"
    
    params = {
        "search": query, "select": "id", "per_page": 1
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        
        if results:
            return {"id": normalize_openalex_id(results[0]["id"])}
        else:
            return {"id": None}
    except Exception as e:
        return {"error": str(e)}