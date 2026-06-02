"""
Flask Blueprint for /query endpoint.

Provides bidirectional translation between URL, OQL, and OQO query formats,
plus a real execution surface (#306) that accepts an OQO directly and returns
ES results — the same response shape as /works, /authors, etc.
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
    apply_grouping,
    apply_sorting,
    execute_search,
    format_response,
    set_source,
)
from core.preference import clean_preference, combine_preferences
from core.properties import ENTITY_PROPERTIES, get_entity_properties
from core.utils import get_data_version_connection
from core.utils import get_display_name as _get_display_name
from query_translation.oqo import OQO, VALID_OPERATORS, filter_from_dict
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oqo_to_es import (
    OQOTranslationError,
    oqo_to_search_and_filter_q,
)
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.oql_tree_renderer import render_oqo_to_oql_and_tree
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import (
    URLRenderError,
    can_render_to_url,
    render_oqo_to_url,
)
from query_translation.validator import (
    ValidationError,
    ValidationResult,
    validate_oqo,
    _has_search_clause,
)


# Entity types that exist in Elasticsearch and can be looked up
NATIVE_ENTITY_TYPES = {
    "institutions", "authors", "sources", "publishers", "funders",
    "topics", "subfields", "fields", "domains", "keywords", "concepts"
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
# Entity dispatch — maps OQO `get_rows` to (fields_dict, index_name, default_sort).
#
# Kept as a function (not a static dict) so we can lazily import per-entity
# modules and pick walden vs legacy indexes based on request data version.
# ---------------------------------------------------------------------------


def _resolve_entity(entity_type: str, connection: str):
    """Return (fields_dict, index_name, default_sort, MessageSchema) for an OQO `get_rows`.

    Raises APIQueryParamsError on unknown entity types so the caller surfaces a 400.
    """
    et = entity_type
    if et == "works":
        from works.fields import fields_dict
        from works.schemas import MessageSchema
        from settings import WORKS_INDEX_LEGACY, WORKS_INDEX_WALDEN

        index_name = (
            WORKS_INDEX_WALDEN if connection == "walden" else WORKS_INDEX_LEGACY
        )
        return fields_dict, index_name, [
            "-cited_by_percentile_year.max",
            "-cited_by_count",
            "id",
        ], MessageSchema
    if et == "authors":
        from authors.fields import fields_dict
        from authors.schemas import MessageSchema
        from settings import AUTHORS_INDEX_LEGACY, AUTHORS_INDEX_WALDEN

        index_name = (
            AUTHORS_INDEX_WALDEN
            if connection == "walden"
            else AUTHORS_INDEX_LEGACY
        )
        return fields_dict, index_name, ["-works_count", "id"], MessageSchema
    if et == "institutions":
        from institutions.fields import fields_dict
        from institutions.schemas import MessageSchema
        from settings import INSTITUTIONS_INDEX

        return fields_dict, INSTITUTIONS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "sources":
        from sources.fields import fields_dict
        from sources.schemas import MessageSchema
        from settings import SOURCES_INDEX

        return fields_dict, SOURCES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "publishers":
        from publishers.fields import fields_dict
        from publishers.schemas import MessageSchema
        from settings import PUBLISHERS_INDEX

        return fields_dict, PUBLISHERS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "funders":
        from funders.fields import fields_dict
        from funders.schemas import MessageSchema
        from settings import FUNDERS_INDEX

        return fields_dict, FUNDERS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "topics":
        from topics.fields import fields_dict
        from topics.schemas import MessageSchema
        from settings import TOPICS_INDEX

        return fields_dict, TOPICS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "keywords":
        from keywords.fields import fields_dict
        from keywords.schemas import MessageSchema
        from settings import KEYWORDS_INDEX

        return fields_dict, KEYWORDS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "concepts":
        from concepts.fields import fields_dict
        from concepts.schemas import MessageSchema
        from settings import CONCEPTS_INDEX

        return fields_dict, CONCEPTS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "sdgs":
        from sdgs.fields import fields_dict
        from sdgs.schemas import MessageSchema
        from settings import SDGS_INDEX

        return fields_dict, SDGS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "domains":
        from domains.fields import fields_dict
        from domains.schemas import MessageSchema
        from settings import DOMAINS_INDEX

        return fields_dict, DOMAINS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "fields":
        from fields.fields import fields_dict
        from fields.schemas import MessageSchema
        from settings import FIELDS_INDEX

        return fields_dict, FIELDS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "subfields":
        from subfields.fields import fields_dict
        from subfields.schemas import MessageSchema
        from settings import SUBFIELDS_INDEX

        return fields_dict, SUBFIELDS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "countries":
        from countries.fields import fields_dict
        from countries.schemas import MessageSchema
        from settings import COUNTRIES_INDEX

        return fields_dict, COUNTRIES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "continents":
        from continents.fields import fields_dict
        from continents.schemas import MessageSchema
        from settings import CONTINENTS_INDEX

        return fields_dict, CONTINENTS_INDEX, ["-works_count", "id"], MessageSchema
    if et == "languages":
        from languages.fields import fields_dict
        from languages.schemas import MessageSchema
        from settings import LANGUAGES_INDEX

        return fields_dict, LANGUAGES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "licenses":
        from licenses.fields import fields_dict
        from licenses.schemas import MessageSchema
        from settings import LICENSES_INDEX

        return fields_dict, LICENSES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "source-types":
        from source_types.fields import fields_dict
        from source_types.schemas import MessageSchema
        from settings import SOURCE_TYPES_INDEX

        return fields_dict, SOURCE_TYPES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "institution-types":
        from institution_types.fields import fields_dict
        from institution_types.schemas import MessageSchema
        from settings import INSTITUTION_TYPES_INDEX

        return (
            fields_dict,
            INSTITUTION_TYPES_INDEX,
            ["-works_count", "id"],
            MessageSchema,
        )
    if et in ("work-types", "types"):
        from work_types.fields import fields_dict
        from work_types.schemas import MessageSchema
        from settings import WORK_TYPES_INDEX

        return fields_dict, WORK_TYPES_INDEX, ["-works_count", "id"], MessageSchema
    if et == "awards":
        from awards.fields import fields_dict
        from awards.schemas import MessageSchema
        from settings import AWARDS_INDEX

        return fields_dict, AWARDS_INDEX, ["-funded_outputs_count", "id"], MessageSchema
    if et == "locations":
        # locations live only in walden; the legacy view hardcodes connection='walden'
        # and its index constant lives in the view, not settings.py. Mirror both,
        # including its locations-specific ascending default sort (#334).
        from locations.fields import fields_dict
        from locations.schemas import MessageSchema
        from locations.views import LOCATIONS_INDEX

        return fields_dict, LOCATIONS_INDEX, ["work_id", "native_id"], MessageSchema

    raise APIQueryParamsError(
        f"OQO get_rows='{entity_type}' is not a supported entity type."
    )


# ---------------------------------------------------------------------------
# Synthetic params dict — mirrors what core/params.py:parse_params would produce
# from a URL request, so we can reuse the downstream shared_view stages
# (apply_sorting, apply_grouping, execute_search, format_response) untouched.
# ---------------------------------------------------------------------------


def _set_int_arg(request, name, default):
    raw = request.args.get(name) or request.args.get(name.replace("-", "_"))
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise APIQueryParamsError(f"Param {name} must be an integer.")


def _build_params_from_oqo(oqo: OQO, request):
    """Synthesize the params dict that shared_view stages expect, from the OQO.

    Logistics layer (#318): pagination (`per_page`/`page`/`cursor`) and the
    sample `seed` are read FROM THE OQO so the object is self-contained — the
    cacheable `/query/oqo/<json>` form then carries everything with no
    side-channel query string. For back-compat with callers that still pass them
    on the query string, the request args remain a fallback when the OQO omits
    a value (the OQO always wins when it carries one).

    `filters` is set to None because filters are applied directly via the
    pre-built Q (returned by the translator). `search`, `searches`, etc. are
    None — the OQO surface doesn't expose ?search yet; that's a deliberate
    follow-up.
    """
    sort = None
    if oqo.sort_by:
        # Rebuild the legacy ordered {column: direction} sort dict from the
        # ordered sort-key list. This is faithful to legacy
        # core/utils.py:map_sort_params: insertion order is preserved (Py3.7+
        # dict) so multi-column tiebreakers apply primary→secondary, and a
        # duplicate column collapses to its last direction (same as legacy).
        # "asc" default matches legacy for a directionless sort (#323 Pattern F1).
        sort = {s.column_id: (s.direction or "asc") for s in oqo.sort_by}

    # Search-awareness for sorting (#323 2b/2c). `apply_sorting` decides the
    # implicit default sort and gates `relevance_score` via
    # `check_is_search_query(params["filters"], params["search"])`. The OQO path
    # applies the actual search via the pre-built Q (not params), so we signal a
    # search clause by setting params["search"] truthy when any `*.search` leaf
    # is present (incl. `default.search`, which is where a top-level `?search=`
    # lands). With a search clause + no explicit sort, legacy `apply_sorting`
    # then applies `_score, publication_date, id` for works (order parity); and
    # `relevance_score` sort maps to ES `_score` instead of 400-ing. No other
    # stage the OQO executor runs reads params["search"], so this only affects
    # sort — there is no second search application.
    has_search = _has_search_clause(oqo.filter_rows)

    group_by = None
    if oqo.group_by:
        if len(oqo.group_by) > 1:
            raise APIQueryParamsError(
                "Multi-dimensional group_by is in the OQO spec but not yet "
                "supported by the live API. See oxjob #297."
            )
        group_by = oqo.group_by[0].column_id

    # OQO value wins; request arg is the back-compat fallback.
    cursor = oqo.cursor if oqo.cursor is not None else request.args.get("cursor")
    page = oqo.page if oqo.page is not None else _set_int_arg(request, "page", 1)
    per_page = oqo.per_page if oqo.per_page is not None else get_per_page(request)
    seed = oqo.seed if oqo.seed is not None else request.args.get("seed")

    return {
        "apc_sum": None,
        "cited_by_count_sum": None,
        "cursor": cursor,
        "format": None,
        "filters": None,
        "group_by": group_by,
        "group_bys": None,
        "page": page,
        "per_page": per_page,
        "sample": oqo.sample,
        "seed": seed,
        "q": None,
        "search": "<oqo-search>" if has_search else None,
        "search_type": None,
        "search_scope": None,
        "searches": [],
        "sort": sort,
    }


# ---------------------------------------------------------------------------
# /registry — the entity-property catalog (#331; formerly #294 Phase B)
# ---------------------------------------------------------------------------


def _serialize_entity(properties):
    """Serialize one entity's {name: Property} into {name: dict}."""
    return {name: prop.serialize() for name, prop in properties.items()}


@blueprint.route("/registry", methods=["GET"])
def get_registry():
    """The full entity-property catalog: every queryable property per entity,
    with its value type, valid filter operators, actions, and cross-type
    entity_type.

    Built at boot from the live `Field` objects the filter layer executes
    (core/properties.py), so it can't drift from what the server actually accepts.
    This is the same data the OQO validator consults to answer "is column X
    valid on entity Y with operator Z and value type T?".
    """
    return jsonify(
        {
            "meta": {
                "entity_count": len(ENTITY_PROPERTIES),
                "column_count": sum(
                    len(props) for props in ENTITY_PROPERTIES.values()
                ),
            },
            "registry": {
                entity: _serialize_entity(props)
                for entity, props in ENTITY_PROPERTIES.items()
            },
        }
    ), 200


@blueprint.route("/registry/<entity_type>", methods=["GET"])
def get_registry_entity(entity_type: str):
    """The property catalog for a single entity type, e.g. `/registry/works`."""
    properties = get_entity_properties(entity_type)
    if properties is None:
        return _error_response(
            f"'{entity_type}' is not a registered entity type.",
            "invalid_entity",
            status=404,
        )
    return jsonify(
        {
            "meta": {"entity_type": entity_type, "column_count": len(properties)},
            "columns": _serialize_entity(properties),
        }
    ), 200


# ---------------------------------------------------------------------------
# /query — the OQO execution surface (#306)
# ---------------------------------------------------------------------------


@blueprint.route("/query", methods=["POST"])
def post_query():
    """Execute an OQO directly against Elasticsearch.

    Request body: JSON OQO (see docs/oqo-schema.json).
    Optional query-string params: per-page, cursor, page (transport-level
    pagination, identical to the URL surface).

    Response shape mirrors /works, /authors, etc.: {meta, group_by, results}.
    Adds `"oqo"` (canonicalized echo of the input) for round-trip introspection.
    """
    if not request.is_json:
        return _error_response(
            "Request body must be JSON (Content-Type: application/json).",
            "invalid_content_type",
            status=400,
        )

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response(
            "Request body must be a JSON object representing an OQO.",
            "invalid_body",
            status=400,
        )

    return _execute_oqo(body)


@blueprint.route("/query/oqo/<path:oqo_encoded>", methods=["GET"])
def get_query_by_oqo(oqo_encoded: str):
    """Path-form OQO read endpoint (cacheable).

    The OQO carries the entity type (`get_rows`), so the route can't live under
    an entity-specific prefix like `/works`. The path is `/query/oqo/<json>`,
    where `<json>` is the URL-encoded JSON OQO.
    """
    try:
        oqo_decoded = urllib.parse.unquote(oqo_encoded)
        body = json.loads(oqo_decoded)
    except ValueError as e:
        return _error_response(
            f"OQO path is not valid JSON: {e}",
            "invalid_oqo_json",
            status=400,
        )

    if not isinstance(body, dict):
        return _error_response(
            "OQO path must decode to a JSON object.",
            "invalid_oqo_json",
            status=400,
        )

    return _execute_oqo(body)


def _execute_oqo(oqo_dict: dict):
    """Shared body for the POST and GET-path-form handlers."""
    # Parse the OQO from the raw dict. KeyError / TypeError / ValueError here
    # are surface-level shape errors — return 400, not 500.
    try:
        oqo = OQO.from_dict(oqo_dict)
    except (KeyError, TypeError, ValueError) as e:
        return _error_response(
            f"Could not parse OQO: {e}",
            "invalid_oqo",
            status=400,
        )

    # Validate the OQO against the field registry. Returns structured errors.
    validation = validate_oqo(oqo)
    if not validation.valid:
        return jsonify(
            {
                "oqo": oqo.to_dict(),
                "validation": validation.to_dict(),
            }
        ), 400

    # Validate leaf operators explicitly (the validator already does this, but
    # the schema-level check is "valid operator string" — we want to surface a
    # 400 for any operator not in VALID_OPERATORS so we never trip a 500 down
    # in the translator).
    invalid_ops = _collect_invalid_operators(oqo.filter_rows)
    if invalid_ops:
        return jsonify(
            {
                "oqo": oqo.to_dict(),
                "validation": {
                    "valid": False,
                    "errors": [
                        {
                            "type": "invalid_operator",
                            "message": (
                                f"Operator '{op}' is not valid. "
                                f"Valid operators: {sorted(VALID_OPERATORS)}"
                            ),
                            "location": loc,
                        }
                        for (op, loc) in invalid_ops
                    ],
                    "warnings": [],
                },
            }
        ), 400

    # Dispatch to per-entity fields_dict + index_name + serialization schema.
    connection = get_data_version_connection(request)
    try:
        fields_dict, index_name, default_sort, MessageSchema = _resolve_entity(
            oqo.get_rows, connection
        )
    except APIQueryParamsError as e:
        return _error_response(str(e), "invalid_entity", status=400)

    # Build the synthetic params dict that downstream shared_view stages expect.
    try:
        params = _build_params_from_oqo(oqo, request)
    except APIQueryParamsError as e:
        return _error_response(str(e), "invalid_params", status=400)

    # Translate the OQO filter tree, splitting `.search` (scoring) clauses from
    # exact filters so search runs in *query* context (relevance scoring) and
    # filters in *filter* context — exactly like legacy construct_query. Applying
    # search via s.filter() would leave _score uniform and silently break
    # relevance ordering (#323). When sampling, legacy applies search via
    # s.filter(), so we pass scoring=False to keep parity.
    try:
        search_q, filter_q = oqo_to_search_and_filter_q(
            oqo, fields_dict, scoring=not oqo.sample
        )
    except OQOTranslationError as e:
        return _error_response(str(e), "translation_error", status=400)

    # Apply the standard works-walden is_xpac:false default unless the OQO
    # already references is_xpac or the caller opts in via include_xpac=true.
    from elasticsearch_dsl import Q

    extra_qs = []
    if oqo.get_rows == "works" and connection == "walden":
        include_xpac = (
            request.args.get("include_xpac") == "true"
            or request.args.get("include-xpac") == "true"
        )
        oqo_mentions_xpac = _oqo_mentions_column(oqo.filter_rows, "is_xpac")
        if not include_xpac and not oqo_mentions_xpac:
            extra_qs.append(Q("term", is_xpac="false"))

    # Mirror the /authors works_count>0 default (authors/views.py, #287): hide
    # curation-emptied (0-works) authors unless the OQO explicitly references
    # works_count. Without this the OQO over-counts authors vs legacy (#323
    # Pattern B). Applies on every connection, matching the legacy view.
    if oqo.get_rows == "authors":
        if not _oqo_mentions_column(oqo.filter_rows, "works_count"):
            extra_qs.append(Q("range", works_count={"gt": 0}))

    # Custom group_by results (continent / version / best_open_version) are
    # computed at format time by core/group_by/custom_results.py, which rebuilds a
    # fresh Search from params["filters"]/params["search"] via search_and_filter().
    # The OQO path leaves those params unset (it applies filters/search via the
    # pre-built Qs above), so without this those sub-searches would run UNFILTERED
    # → global bucket counts (#323 Pattern G2). Stash the exact query/filter
    # contexts of the main search so the custom path can replicate them. extra_qs
    # (the is_xpac:false default) is folded into the filter list so bucket totals
    # match meta.count. Plain dict keys; legacy never sets them, so it's untouched.
    s = Search(index=index_name, using=connection)
    params["_oqo_search_q"] = search_q
    params["_oqo_filter_qs"] = ([filter_q] if filter_q is not None else []) + extra_qs
    s = set_source(index_name, s)
    s = _set_size(params, s)
    s = _set_cursor_pagination(params, s)
    if search_q is not None:
        s = s.query(search_q)
    if filter_q is not None:
        s = s.filter(filter_q)
    for extra in extra_qs:
        s = s.filter(extra)
    s = _apply_search_preference(oqo, s)
    s = apply_sorting(params, fields_dict, default_sort, index_name, s)
    s = apply_grouping(params, fields_dict, s)

    # Execute + format.
    try:
        response = execute_search(s, params)
    except APIError:
        raise
    except Exception as e:  # pragma: no cover — defensive
        return _error_response(
            f"Elasticsearch error: {e}",
            "es_error",
            status=500,
        )

    result = format_response(response, params, index_name, fields_dict, s, connection)
    # Marshall the ES response objects into JSON-serializable dicts via the
    # entity's MessageSchema — the same path the per-entity views use. Apply the
    # OQO `select` projection (#318) the same way `core.utils.process_only_fields`
    # does for the URL `?select=`: marshmallow `only` of `results.<field>` plus
    # the always-present `meta`/`group_by` envelope. select columns were already
    # validated against the entity's selectable fields, so they're safe here.
    only_fields = None
    if oqo.select:
        only_fields = (
            ["meta"]
            + [f"results.{f}" for f in oqo.select]
            + ["group_by"]
        )
    message_schema = MessageSchema(only=only_fields) if only_fields else MessageSchema()
    serialized = message_schema.dump(result)
    # Echo a canonicalized OQO so clients can confirm what we actually executed.
    serialized["oqo"] = canonicalize_oqo(oqo).to_dict()
    return jsonify(serialized), 200


def _error_response(message, error_type, status=400):
    return jsonify(
        {
            "validation": {
                "valid": False,
                "errors": [
                    {"type": error_type, "message": message, "location": None}
                ],
                "warnings": [],
            }
        }
    ), status


def _collect_invalid_operators(filter_rows, prefix="filter_rows"):
    bad = []
    for i, f in enumerate(filter_rows):
        loc = f"{prefix}[{i}]"
        if hasattr(f, "operator"):
            if f.operator not in VALID_OPERATORS:
                bad.append((f.operator, loc))
        if hasattr(f, "filters"):
            bad.extend(_collect_invalid_operators(f.filters, loc + ".filters"))
    return bad


# The search clauses legacy pins ES shard routing on (#323 Pattern C). Legacy sets
# preference=clean_preference(<value>) for a `?search=` query (which lands in the
# OQO as a `default.search` filter) and for the four `*.search` filters that
# core/shared_view.set_preference_for_filter_search inspects. Other search kinds
# (fulltext/keyword/semantic) get no preference in legacy, so they're excluded here
# for parity. Empirically verified against the legacy path (see EXPLORE session 5).
PREFERENCE_SEARCH_COLUMNS = {
    "default.search",
    "title.search",
    "abstract.search",
    "display_name.search",
    "raw_affiliation_strings.search",
}


def _collect_preference_search_values(filter_rows):
    """The search-clause values legacy would pin shard `preference` on, in order."""
    vals = []
    for f in filter_rows:
        if hasattr(f, "filters"):
            vals.extend(_collect_preference_search_values(f.filters))
        elif (
            getattr(f, "column_id", None) in PREFERENCE_SEARCH_COLUMNS
            and isinstance(getattr(f, "value", None), str)
        ):
            vals.append(f.value)
    return vals


def _apply_search_preference(oqo, s):
    """Pin ES shard routing the way legacy does for search queries (#323 Pattern C).

    The OQO executor otherwise sets no `preference`, so legacy (preference pinned by
    the search string) and the OQO path route to different shards → divergent score
    tie-breaks among near-equal-relevance docs. Mirror legacy: single search clause →
    clean_preference(value); multiple → combine_preferences (legacy's multi-search
    path). No eligible search clause → no preference (matches legacy filter-only).
    """
    values = _collect_preference_search_values(oqo.filter_rows)
    if len(values) == 1:
        return s.params(preference=clean_preference(values[0]))
    if len(values) > 1:
        return s.params(preference=combine_preferences(values))
    return s


def _oqo_mentions_column(filter_rows, column_id):
    for f in filter_rows:
        if hasattr(f, "column_id") and f.column_id == column_id:
            return True
        if hasattr(f, "filters") and _oqo_mentions_column(f.filters, column_id):
            return True
    return False


def _set_size(params, s):
    if params["group_by"]:
        return s.extra(size=0, track_total_hits=True)
    return s.extra(size=params["per_page"], track_total_hits=True)


def _set_cursor_pagination(params, s):
    if not params["group_by"]:
        return handle_cursor(params["cursor"], params["page"], s)
    return s


# ---------------------------------------------------------------------------
# Legacy /query GET (format-translation introspection) — deferred to a future
# rev; the route below preserves a usable shape but is no longer the 404 stub.
# ---------------------------------------------------------------------------


@blueprint.route("/query", methods=["GET"])
def get_query():
    """Backwards-compat translation introspection.

    No body — returns a small descriptor so existing callers don't 404.
    To execute an OQO directly use `POST /query` (with a JSON body) or
    `GET /query/oqo/<urlencoded_json>`.
    """
    return jsonify(
        {
            "msg": (
                "POST /query with an OQO JSON body, or use "
                "GET /query/oqo/<urlencoded_json> for the cacheable read form."
            ),
            "documentation_url": "/docs",
        }
    ), 200

    # ---- legacy translation-introspection code, kept commented for reference ----
    # entity_type = request.args.get("entity_type", "works")
    # filter_string = request.args.get("filter")
    # sort_string = request.args.get("sort")
    # sample = request.args.get("sample", type=int)
    # oqo_json = request.args.get("oqo")
    #
    # try:
    #     oqo = None
    #     parse_error = None
    #
    #     if oqo_json:
    #         # Parse OQO from JSON query param
    #         oqo, parse_error = parse_oqo_input(entity_type, oqo_json)
    #     else:
    #         # Parse from URL filter/sort params
    #         oqo, parse_error = parse_url_input(entity_type, {
    #             "filter": filter_string,
    #             "sort": sort_string,
    #             "sample": sample
    #         })
    #
    #     if parse_error:
    #         return jsonify({
    #             "url": None,
    #             "oql": None,
    #             "oqo": None,
    #             "validation": {
    #                 "valid": False,
    #                 "errors": [{"type": "parse_error", "message": parse_error}],
    #                 "warnings": []
    #             }
    #         }), 400
    #
    #     validation_result = validate_oqo(oqo)
    #
    #     if not validation_result.valid:
    #         return jsonify({
    #             "url": None,
    #             "oql": None,
    #             "oqo": oqo.to_dict(),
    #             "validation": validation_result.to_dict()
    #         }), 400
    #
    #     response = render_all_formats(oqo, validation_result)
    #     return jsonify(response), 200
    #
    # except Exception as e:
    #     return jsonify({
    #         "url": None,
    #         "oql": None,
    #         "oqo": None,
    #         "validation": {
    #             "valid": False,
    #             "errors": [{"type": "internal_error", "message": str(e)}],
    #             "warnings": []
    #         }
    #     }), 500


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
            entity_type=entity_type,
            filter_string=filter_string,
            sort_string=sort_string,
            sample=sample,
            group_by_string=group_by_string,
            select_string=select_string,
            seed=seed,
            per_page=per_page,
            page=page,
            cursor=cursor,
            search_string=search_string,
        )
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
    """Render OQO to all output formats."""
    warnings = list(validation_result.warnings)
    
    # Canonicalize OQO for deterministic output
    canonical_oqo = canonicalize_oqo(oqo)
    
    # Render to URL
    url_output = None
    try:
        url_output = render_oqo_to_url(canonical_oqo)
    except URLRenderError as e:
        warnings.append(ValidationError(
            type="url_not_representable",
            message=str(e)
        ))
    
    # Render to OQL and oql_render tree
    # Pass safe_get_display_name as entity resolver to include display names in oql_render
    oql_output, oql_render_tree = render_oqo_to_oql_and_tree(
        canonical_oqo,
        entity_resolver=safe_get_display_name
    )
    
    # Build response
    return {
        "url": url_output,
        "oql": oql_output,
        "oql_render": oql_render_tree.to_dict(),
        "oqo": canonical_oqo.to_dict(),
        "validation": {
            "valid": True,
            "errors": [],
            "warnings": [
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
        "type": "json_schema",
        "name": "OpenAlex_Query_Object",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "verbosity": "low"
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
    #             "url": None,
    #             "oql": None,
    #             "oqo": None,
    #             "validation": {
    #                 "valid": False,
    #                 "errors": [{"type": "parse_error", "message": parse_error}],
    #                 "warnings": []
    #             }
    #         }), 400
    #
    #     validation_result = validate_oqo(oqo)
    #
    #     if not validation_result.valid:
    #         return jsonify({
    #             "url": None,
    #             "oql": None,
    #             "oqo": oqo.to_dict(),
    #             "validation": validation_result.to_dict()
    #         }), 400
    #
    #     response = render_all_formats(oqo, validation_result)
    #     response["meta"] = {"timing": timing_meta}
    #     return jsonify(response), 200
    #
    # except Exception as e:
    #     return jsonify({
    #         "url": None,
    #         "oql": None,
    #         "oqo": None,
    #         "validation": {
    #             "valid": False,
    #             "errors": [{"type": "internal_error", "message": str(e)}],
    #             "warnings": []
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
        "openai_calls": [],
        "tool_calls": [],
    }
    total_start = time.time()
    
    # Initial call with stored prompt and variables
    openai_start = time.time()
    response = client.responses.create(
        model=OPENAI_MODEL,
        prompt={
            "id": OPENAI_PROMPT_ID,
            "variables": {
                "query": natural_language_query
            }
        },
        input=[],
        text=TEXT_CONFIG,
        reasoning=REASONING_CONFIG,
        store=True
    )
    openai_elapsed = time.time() - openai_start
    timing["openai_calls"].append({
        "call_number": 1,
        "duration_ms": round(openai_elapsed * 1000, 1),
        "had_tool_calls": any(item.type == "function_call" for item in response.output)
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
                    "type": "reasoning",
                    "id": item.id,
                    "summary": [{"type": "summary_text", "text": s.text} for s in (item.summary or [])],
                    "encrypted_content": getattr(item, 'encrypted_content', '')
                })
            elif item.type == "function_call":
                follow_up_input.append({
                    "type": "function_call",
                    "id": item.id,
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments
                })
        
        # Execute tool calls in parallel and add outputs
        tool_start = time.time()
        tool_results = execute_tool_calls_parallel(tool_calls)
        tool_elapsed = time.time() - tool_start
        
        tool_call_info = {
            "iteration": iteration,
            "num_calls": len(tool_calls),
            "duration_ms": round(tool_elapsed * 1000, 1),
            "calls": [
                {
                    "entity_type": json.loads(tc.arguments).get("entity_type"),
                    "query": json.loads(tc.arguments).get("query")
                }
                for tc in tool_calls
            ]
        }
        timing["tool_calls"].append(tool_call_info)
        
        for tool_call, result in zip(tool_calls, tool_results):
            follow_up_input.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(result)
            })
        
        # Make follow-up call with full conversation
        openai_start = time.time()
        response = client.responses.create(
            model=OPENAI_MODEL,
            prompt={
                "id": OPENAI_PROMPT_ID,
                "variables": {
                    "query": natural_language_query
                }
            },
            input=follow_up_input,
            text=TEXT_CONFIG,
            reasoning=REASONING_CONFIG,
            store=True
        )
        openai_elapsed = time.time() - openai_start
        timing["openai_calls"].append({
            "call_number": len(timing["openai_calls"]) + 1,
            "duration_ms": round(openai_elapsed * 1000, 1),
            "had_tool_calls": any(item.type == "function_call" for item in response.output)
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
        "search": query,
        "select": "id",
        "per_page": 1
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
