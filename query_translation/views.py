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

import settings
from core.cursor import handle_cursor
from core.exceptions import APIError, APIQueryParamsError
from core.paginate import get_pagination, get_per_page
from core.shared_view import (
    apply_grouping, apply_sorting, execute_search, format_response, set_source, )
from core.preference import clean_preference, combine_preferences
from core.properties import get_entity_properties, render_properties
from core.utils import get_data_version_connection
from query_translation.oqo import OQO, VALID_OPERATORS, filter_from_dict
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oqo_to_es import (
    OQOTranslationError, oqo_to_search_and_filter_q, )
from query_translation.oql_parser import OQLParseError, parse_oql_to_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.oql_tree_renderer import render_oqo_to_oql_and_tree
from query_translation.url_parser import fold_scoped_search_params, parse_url_to_oqo
from query_translation.url_renderer import (
    URLRenderError, can_render_to_url, render_oqo_to_url, )
from query_translation.x_query import (
    _components_to_oxurl, safe_get_display_name, )
from query_translation.validator import (
    ValidationError, ValidationResult, validate_oqo, _has_search_clause, )


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

    # Fold scoped search params (search.title_and_abstract[.exact]=…) into filter
    # clauses. Pure helper in url_parser so the offline tests/oql gate covers it.
    folded_filter = fold_scoped_search_params(params)
    if folded_filter is not None:
        params["filter"] = folded_filter

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
    """Translate an OQL string to all formats (no execution / no ES).

    Unlike the oxurl route, the value here is ONLY the path segment — an OQL
    string has no `?`, so the request's own query params (`?mailto=…`,
    `?api_key=…`) must never be folded back in. Folding them made the parser
    read the querystring as OQL tokens ("two conditions with no AND/OR between
    them near '?mailto=…'") for any caller sending standard meta params (#428).
    Callers must URL-encode the OQL (the GUI does).
    """
    try:
        oqo = parse_oql_to_oqo(value)
    except Exception as e:  # OQLParseError and friends → 400
        return _error_response(f"Failed to parse OQL: {e}", "parse_error", status=400)
    return _translate_response(oqo, None)


@blueprint.route("/query/oqo/<path:value>", methods=["GET"])
def translate_oqo(value: str):
    """Translate an OQO (URL-encoded or raw JSON) to all formats (no execution / no ES).

    Same contract as /query/oql: the value is only the path segment; request
    query params (`?mailto=…`) are never part of the OQO JSON (#428).
    """
    oqo, err = parse_oqo_input(None, value)
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
            semantic_search_string = input_data.get("search.semantic")
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
            semantic_search_string = None

        oqo = parse_url_to_oqo(
            entity_type=entity_type, filter_string=filter_string, sort_string=sort_string, sample=sample, group_by_string=group_by_string, select_string=select_string, seed=seed, per_page=per_page, page=page, cursor=cursor, search_string=search_string, semantic_search_string=semantic_search_string, )
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


@blueprint.route("/query/natural-language/<path:natural_language_query>", methods=["GET"])
def get_natural_language_query(natural_language_query: str):
    """Translate a plain-English query to OQO via Claude tool-calling, then render
    all formats — the NL sibling of `/query/{oql,oxurl,oqo}/<q>`.

    Like the rest of this resource it is TRANSLATION ONLY (returns
    {oxurl, oql, oql_render, oqo, validation} + meta); it does not execute. The
    client can run the returned `oqo` via the root execution endpoint (`/?oqo=`).

    Backed by `query_translation/nl_to_oqo.py` (oxjob #344, Claude Haiku 4.5 +
    prompt caching). Soft dependency: returns 503 if no CLAUDE_API_KEY /
    ANTHROPIC_API_KEY is configured, and 502 if the model returns no valid OQO.
    """
    import os

    if not (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        return jsonify({"error": "natural-language translation is not configured "
                                 "(no Anthropic API key)"}), 503

    from query_translation.nl_to_oqo import nl_to_oqo

    start = time.time()
    try:
        result = nl_to_oqo(natural_language_query)
    except Exception as e:
        return jsonify({"error": f"natural-language translation failed: {e}"}), 502
    elapsed_ms = round((time.time() - start) * 1000, 1)

    if result.get("error") or not result.get("oqo"):
        # Includes the structured refusal path (e.g. collections out of scope).
        status = 422 if result.get("refused") else 502
        return jsonify({
            "oxurl": None, "oql": None, "oqo": None,
            "validation": {"valid": False,
                           "errors": [{"type": "nl_translation_error",
                                       "message": result.get("error") or "no OQO produced"}],
                           "warnings": []},
            "meta": {"timing": {"total_ms": elapsed_ms}},
        }), status

    oqo = OQO.from_dict(result["oqo"])
    validation_result = validate_oqo(oqo)
    response = render_all_formats(oqo, validation_result)
    response["meta"] = {"timing": {"total_ms": elapsed_ms},
                        "usage": result.get("usage")}
    return jsonify(response), 200
