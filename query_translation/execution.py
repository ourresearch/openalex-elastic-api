"""OQO / OQL **execution** engine for the root query surface (#306, #372 Phase 3).

This module HITS ELASTICSEARCH. It is the back end of the *execution* routes that
live at the application root in `works/views.py`:

    GET  /?oql=<oql>          POST /  {"oql": "..."}
    GET  /?oqo=<oqo-json>     POST /  {"oqo": {...}}

`works/views.py` lazily imports the public `execute_*` wrappers below and calls
them; nothing here registers a route of its own.

NOT to be confused with the **translation** resource in `query_translation/views.py`
(`GET /query/{oxurl|oql|oqo}/<q>`), which only parses + renders the query into all
formats and NEVER touches ES. Execution was split out of `views.py` (oxjob #384) so
the translation module no longer cohabits with the ES-executing machinery — a
recurring source of "does /query run the query?" confusion.
"""
import importlib
import json
from dataclasses import replace

from elasticsearch_dsl import Q, Search
from flask import jsonify, request

import settings
from core.cursor import handle_cursor
from core.exceptions import APIError, APIQueryParamsError
from core.paginate import get_per_page
from core.preference import clean_preference, combine_preferences
from core.shared_view import (
    add_semantic_search,
    apply_grouping,
    apply_sorting,
    execute_search,
    format_response,
    set_source,
)
from core.utils import get_data_version_connection, map_filter_params, map_sort_params
from core.vector_index import vector_semantic_search
from query_translation.oqo import OQO, SortBy, canonicalize_oqo_column_ids
from query_translation.oqo_to_es import (
    OQOTranslationError,
    oqo_to_search_and_filter_q,
)
from query_translation.oql_parser import OQLParseError, parse_oql_to_oqo
from query_translation.url_renderer import (
    URLRenderError,
    _extract_semantic,
    render_filters,
)
from query_translation.validator import validate_oqo, _has_search_clause

# Shared response/render helpers. `build_x_query` lives in the dependency-light
# `x_query` module (shared with `core.shared_view`, #378); `_error_response` stays
# with the translation resource. No cycle either way.
from query_translation.x_query import build_x_query
from query_translation.views import _error_response

# ---------------------------------------------------------------------------
# Entity dispatch — maps OQO `get_rows` to (fields_dict, index_name, default_sort).
#
# Kept as a function (not a static dict) so we can lazily import per-entity
# modules and pick walden vs legacy indexes based on request data version.
# ---------------------------------------------------------------------------


# get_rows -> (entity module, settings index constant). Every entity here uses
# the standard ["-works_count", "id"] default sort unless listed in
# _DEFAULT_SORT_OVERRIDES. works / authors / locations need bespoke handling
# (walden-vs-legacy index split, index constant outside settings) and stay
# spelled out in _resolve_entity.
_ENTITY_DISPATCH = {
    "institutions": ("institutions", "INSTITUTIONS_INDEX"),
    "sources": ("sources", "SOURCES_INDEX"),
    "publishers": ("publishers", "PUBLISHERS_INDEX"),
    "funders": ("funders", "FUNDERS_INDEX"),
    "topics": ("topics", "TOPICS_INDEX"),
    "keywords": ("keywords", "KEYWORDS_INDEX"),
    "concepts": ("concepts", "CONCEPTS_INDEX"),
    "sdgs": ("sdgs", "SDGS_INDEX"),
    "domains": ("domains", "DOMAINS_INDEX"),
    "fields": ("fields", "FIELDS_INDEX"),
    "subfields": ("subfields", "SUBFIELDS_INDEX"),
    "countries": ("countries", "COUNTRIES_INDEX"),
    "continents": ("continents", "CONTINENTS_INDEX"),
    "languages": ("languages", "LANGUAGES_INDEX"),
    "licenses": ("licenses", "LICENSES_INDEX"),
    "oa-statuses": ("oa_statuses", "OA_STATUSES_INDEX"),
    "source-types": ("source_types", "SOURCE_TYPES_INDEX"),
    "institution-types": ("institution_types", "INSTITUTION_TYPES_INDEX"),
    "work-types": ("work_types", "WORK_TYPES_INDEX"),
    "types": ("work_types", "WORK_TYPES_INDEX"),
    "awards": ("awards", "AWARDS_INDEX"),
}

_DEFAULT_SORT_OVERRIDES = {
    "awards": ["-funded_outputs_count", "id"],
}


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
    if et == "locations":
        # locations live only in walden; the legacy view hardcodes connection='walden'
        # and its index constant lives in the view, not settings.py. Mirror both,
        # including its locations-specific ascending default sort (#334).
        from locations.fields import fields_dict
        from locations.schemas import MessageSchema
        from locations.views import LOCATIONS_INDEX

        return fields_dict, LOCATIONS_INDEX, ["work_id", "native_id"], MessageSchema

    entry = _ENTITY_DISPATCH.get(et)
    if entry is None:
        raise APIQueryParamsError(
            f"OQO get_rows='{entity_type}' is not a supported entity type."
        )
    module_name, index_attr = entry
    fields_mod = importlib.import_module(f"{module_name}.fields")
    schemas_mod = importlib.import_module(f"{module_name}.schemas")
    default_sort = _DEFAULT_SORT_OVERRIDES.get(et, ["-works_count", "id"])
    return (
        fields_mod.fields_dict,
        getattr(settings, index_attr),
        default_sort,
        schemas_mod.MessageSchema,
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
        # A metric-aggregate group sort (oxjob #389) carries `aggregate`; rebuild
        # the dotted pseudo-field key (`<column>.<metric>`) the legacy group_by
        # path parses (core.group_by.buckets.parse_metric_sort_key /
        # core.sort.get_sort_fields), so the OQO path orders buckets identically.
        sort = {
            (f"{s.column_id}.{s.aggregate}" if s.aggregate else s.column_id): (
                s.direction or "asc"
            )
            for s in oqo.sort_by
        }

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

    # group_by flows to the shared_view stages as the legacy comma-joined string.
    # A single column → single-dim (unchanged). Multiple columns → the NESTED
    # multi-dim path (oxjob #387): apply_grouping/format_response detect the comma
    # and build/format nested buckets. This is the execution half of corpus case
    # 48 ("top topics each year") — render already worked; this makes it run.
    group_by = None
    if oqo.group_by:
        group_by = ",".join(g.column_id for g in oqo.group_by)

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


# Execution moved to the root in #372 Phase 3 (`GET /?oql=…`, `GET /?oqo=…`,
# `POST /` with `{oqo}`/`{oql}`) — oql/oqo embed the entity type, so they belong
# at the root next to `/works?filter=…`, not under `/query/...` (which is now the
# pure *translation* resource). The works-blueprint root handler
# (`works/views.py`) dispatches to the public `execute_*` wrappers below. The old
# `POST /query` and `GET /query/oqo/<path>` execute forms are removed (the GET
# path-form now translates; both had zero consumers — see #372 EXPLORE).


def execute_oqo_dict(oqo_dict):
    """Public entry point: execute an OQO given as a dict → Flask response.

    Response shape mirrors /works, /authors, etc.: {meta, group_by, results},
    plus a canonicalized `oqo` echo for round-trip introspection.
    """
    if not isinstance(oqo_dict, dict):
        return _error_response(
            "OQO must be a JSON object.", "invalid_body", status=400
        )
    return _execute_oqo(oqo_dict)


def execute_oqo_json_string(oqo_str):
    """Public entry point: execute an OQO given as a (URL-decoded) JSON string."""
    try:
        oqo_dict = json.loads(oqo_str)
    except (ValueError, TypeError) as e:
        return _error_response(
            f"Could not parse OQO JSON: {e}", "invalid_oqo", status=400
        )
    return execute_oqo_dict(oqo_dict)


def execute_oql_string(oql_str):
    """Public entry point: execute an OQL string → Flask response."""
    if not oql_str or not oql_str.strip():
        return _error_response("Empty OQL query.", "invalid_oql", status=400)
    try:
        oqo = parse_oql_to_oqo(oql_str)
    except OQLParseError as e:  # surface position + context (#373)
        return _oql_parse_error_response(e)
    except Exception as e:  # any other parse failure → 400, never 500
        return _error_response(
            f"Failed to parse OQL: {e}", "parse_error", status=400
        )
    return _execute_oqo(oqo)


def _merge_classic_sort_select(oqo: OQO, request) -> OQO:
    """Fold the classic `?sort=` / `?select=` query-string params INTO the OQO.

    Sorting and field selection are the OQO's job (#318) — they were removed from
    the OQL *language* (#504) and live as `sort_by` / `select` on the object. But
    for back-compat with the legacy `/works?sort=…&select=…` muscle memory, a
    client hitting `GET /?oql=…&sort=…&select=…` (or `?oqo=…`) expects those to
    take effect. They used to be **silently ignored** (execution built params
    straight off the OQO; the query-string fallback covered only
    per_page/page/cursor/seed) — the classic OQL-adjacent footgun (#631).

    Folding them into the OQO here (rather than into the synthetic params dict)
    means they flow through the SAME machinery as OQO-native sort/select:
    `validate_oqo` (structured 400s on a bad column), `canonicalize_oqo_column_ids`
    (alias spellings like `is_oa`), the `select` projection in
    `_finalize_oqo_response`, and the `meta.x_query` echo — one code path, no
    downstream special-casing, semantic path included.

    Precedence mirrors the per_page/page/cursor/seed fallback: **the OQO wins when
    it already carries a value**; the query-string param is honored only when the
    OQO omits it. (An OQL string never carries sort_by/select — both are gone from
    the language — so `?oql=…&sort=…` always uses the fallback; only an `?oqo=…`
    that already sets sort_by/select overrides the query string.)

    `map_sort_params` raises `APIQueryParamsError` on a malformed `sort` — the
    caller wraps this so that surfaces as a clean 400, never a 500.
    """
    updates = {}

    if not oqo.sort_by:
        sort_map = map_sort_params(request.args.get("sort"))  # may raise
        if sort_map:
            # Insertion order preserved (Py3.7+ dict) → multi-column tiebreaker
            # priority survives, exactly like the legacy URL path.
            updates["sort_by"] = [
                SortBy(column_id=col, direction=direction)
                for col, direction in sort_map.items()
            ]

    if not oqo.select:
        select_param = request.args.get("select")
        if select_param:
            cols = [c.strip() for c in select_param.split(",") if c.strip()]
            if cols:
                updates["select"] = cols

    if not updates:
        return oqo

    # Re-canonicalize the merged OQO so injected sort aliases normalize to one
    # identity (idempotent for the already-canonical filter tree; `select` is
    # intentionally left uncanonicalized, matching legacy `?select=`).
    return canonicalize_oqo_column_ids(replace(oqo, **updates))


def _execute_oqo(oqo_or_dict):
    """Shared body for the POST and GET-path-form handlers. Accepts a parsed
    OQO (the OQL path — already canonicalized at the parse boundary) or a raw
    dict (the OQO-JSON paths)."""
    if isinstance(oqo_or_dict, OQO):
        oqo = oqo_or_dict
    else:
        # Parse the OQO from the raw dict. KeyError / TypeError / ValueError
        # here are surface-level shape errors — return 400, not 500.
        try:
            oqo = OQO.from_dict(oqo_or_dict)
        except (KeyError, TypeError, ValueError) as e:
            return _error_response(
                f"Could not parse OQO: {e}",
                "invalid_oqo",
                status=400,
            )

    # Back-compat: fold classic ?sort=/?select= query-string params into the OQO
    # (when it doesn't already carry them) so they're honored, validated, and
    # echoed like OQO-native sort/select rather than silently ignored (#631).
    try:
        oqo = _merge_classic_sort_select(oqo, request)
    except APIQueryParamsError as e:
        return _error_response(str(e), "invalid_params", status=400)

    # Validate the OQO against the field registry (including per-leaf operator
    # validity). Returns structured errors.
    validation = validate_oqo(oqo)
    if not validation.valid:
        return jsonify(
            {
                "oqo": oqo.to_dict(),
                "validation": validation.to_dict(),
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

    # Semantic (vector) search routing (oxjob #363 — follow-up to Case 30).
    # A `*.search.semantic` leaf is a two-phase kNN over the dedicated vector
    # index, NOT an ordinary `Q` match. Mirror core/shared_view.shared_view:
    # detect it and route to the vector path, feeding it the SAME params the
    # legacy URL path would. Without this an OQO carrying a semantic clause
    # silently runs a plain single-pass match (Case 30 fixed only the OQO→URL
    # render direction; OQO-native execution diverged — same class as the
    # cross-type collection fix). `_extract_semantic` (shared with the renderer)
    # raises URLRenderError for the shapes the single vector param can't carry
    # (negated / >1 / nested), so render and execute agree on what's a valid
    # semantic query.
    try:
        semantic_value, _ = _extract_semantic(oqo.filter_rows)
    except URLRenderError as e:
        return _error_response(str(e), "translation_error", status=400)
    if semantic_value is not None:
        if not index_name.lower().startswith("works"):
            return _error_response(
                "Semantic search is only supported on works.",
                "invalid_params",
                status=400,
            )
        return _execute_semantic_oqo(
            oqo, params, index_name, connection, fields_dict, default_sort,
            MessageSchema,
        )

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

    # Corpus selection for works-walden (#481). The OQO `corpus` field is the
    # first-class signal; map it to the is_xpac base constraint:
    #   core      → is_xpac:false (curated only — the historical default)
    #   expansion → is_xpac:true  (the expansion corpus alone)
    #   all       → no constraint (core + expansion)
    # Precedence lives in _effective_corpus (shared with the semantic path).
    extra_qs = []
    corpus = _effective_corpus(oqo, connection)
    if corpus is not None:
        extra_qs.append(Q("term", is_xpac="false" if corpus == "core" else "true"))

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
    return _finalize_oqo_response(result, oqo, MessageSchema)


def _finalize_oqo_response(result, oqo: OQO, MessageSchema):
    """Serialize an execution result dict and return the Flask response.

    Shared tail of both the normal and the semantic (vector) execution paths.
    Marshalls the ES response objects into JSON-serializable dicts via the
    entity's MessageSchema — the same path the per-entity views use. Applies the
    OQO `select` projection (#318) the same way `core.utils.process_only_fields`
    does for the URL `?select=`: marshmallow `only` of `results.<field>` plus the
    always-present `meta`/`group_by` envelope. select columns were already
    validated against the entity's selectable fields, so they're safe here.

    Attaches the private `meta.x_query` triple {oql, oqo, url} so clients can
    confirm what we executed and rehydrate from it (#373) — injected after
    marshmallow `.dump()` (which would drop an unknown `meta` key), only on this
    execute path (keeps `x_query` off `/works?filter=` and out of
    `/properties`/docs). No entity resolver: `x_query.oql` is canonical bare-ID
    OQL (decision 14, #378 S3) — this hot path does NO per-submit ES
    display-name lookups. NB (#603 round 26b→26c, 2026-07-15): this was briefly
    flipped to annotated (`441b112`) to align with the render canonical after
    the keyword either/or draft-wipe (the #464 Phase 2a URL projection writes
    this string, and its divergence from the annotated render canonical made the
    GUI builder mistake its own query echo for an external change). Jason chose
    the opposite alignment the same day — URLs are BARE: the GUI strips
    annotations at its single URL-serialization point (openalex-gui
    `oqlSerialize.js`), and its `props.oql` watcher recognises the projection
    via `lastExecutedOql`, so bare-vs-annotated can no longer wipe drafts AND
    this path stays lookup-free. Don't re-add a resolver here for display
    reasons; the readable annotated OQL comes from the render endpoints
    (`/query/*`), which the GUI calls per user action, not per execute.
    """
    only_fields = None
    if oqo.select:
        only_fields = (
            ["meta"]
            + [f"results.{f}" for f in oqo.select]
            + ["group_by"]
        )
    message_schema = MessageSchema(only=only_fields) if only_fields else MessageSchema()
    serialized = message_schema.dump(result)
    # Honor the user's authored operand order (charter decision 30, #363/#475): this
    # is the OQL/builder execute path, and the SERP rebuilds `?oql=` from x_query, so
    # sorting commutative value-bag members here would silently alphabetize the user's
    # values. Sorting stays on the legacy-URL path (shared_view) and dedup hash-keys.
    serialized.setdefault("meta", {})["x_query"] = build_x_query(oqo, sort_operands=False)
    return jsonify(serialized), 200


def _execute_semantic_oqo(
    oqo: OQO, params, index_name, connection, fields_dict, default_sort,
    MessageSchema,
):
    """Execute a semantic (vector) OQO, mirroring the legacy URL semantic path.

    The non-semantic filters are rendered to the URL `filter=` string and parsed
    back into the legacy `params["filters"]` list-of-dicts via the SAME helpers
    the URL path uses (`render_filters` + `map_filter_params`) — so OQO-native
    execution feeds the vector index byte-identical filters to the rendered-URL
    path and the two can't diverge (the parity guarantee, same as the cross-type
    collection fix). `_extract_semantic` already validated the semantic clause's
    shape; re-run it here to split off the value + the remaining filter rows.

    Routes exactly like `core/shared_view.shared_view`: the two-phase
    `vector_semantic_search` when `USE_VECTOR_INDEX` is on (the prod path), else
    the single-index `add_semantic_search` kNN fallback.
    """
    semantic_value, remaining_rows = _extract_semantic(oqo.filter_rows)

    params = dict(params)
    params["search"] = semantic_value
    params["search_type"] = "semantic"
    params["searches"] = [
        {"search": semantic_value, "search_type": "semantic", "search_scope": None}
    ]

    # Render the remaining (non-semantic) OQO filters to the URL filter string,
    # then parse to the params list-of-dicts form the vector / kNN pre-filter
    # builders consume. Raises for filter shapes the URL surface (hence the
    # vector path) can't carry (e.g. cross-field OR, nested boolean).
    try:
        filter_string = render_filters(remaining_rows)
    except URLRenderError as e:
        return _error_response(str(e), "translation_error", status=400)
    filters = map_filter_params(filter_string) if filter_string else []
    if filters is None:
        filters = []

    # Corpus selection on the semantic path (#481) — same _effective_corpus
    # precedence as the normal path, rendered to the params filter-dict form.
    # Caveat: the vector index holds only non-xpac works, so the prod vector path
    # can't surface the expansion corpus regardless — that's a known index
    # limitation, not this selector's concern; the single-index fallback honors
    # the kNN pre-filter correctly.
    corpus = _effective_corpus(oqo, connection)
    if corpus is not None:
        filters = filters + [{"is_xpac": "false" if corpus == "core" else "true"}]
    params["filters"] = filters or None

    # Two-phase vector index (the prod path: USE_VECTOR_INDEX=true). Builds and
    # returns the result dict directly, same as shared_view does.
    if settings.USE_VECTOR_INDEX:
        try:
            result = vector_semantic_search(params, index_name, connection)
        except APIQueryParamsError as e:
            return _error_response(str(e), "invalid_params", status=400)
        return _finalize_oqo_response(result, oqo, MessageSchema)

    # Fallback: single-index kNN on the works index (USE_VECTOR_INDEX off),
    # mirroring construct_query's `add_semantic_search` sub-path. Reuses the OQO
    # executor's own pipeline stages (set_source / size / cursor / sort / group)
    # for parity with the normal OQO path rather than legacy's extra stages.
    s = Search(index=index_name, using=connection)
    s = set_source(index_name, s)
    s = _set_size(params, s)
    s = _set_cursor_pagination(params, s)
    try:
        s = add_semantic_search(params, fields_dict, s)
    except APIQueryParamsError as e:
        return _error_response(str(e), "invalid_params", status=400)
    s = apply_sorting(params, fields_dict, default_sort, index_name, s)
    s = apply_grouping(params, fields_dict, s)
    try:
        response = execute_search(s, params)
    except APIError:
        raise
    except Exception as e:  # pragma: no cover — defensive
        return _error_response(f"Elasticsearch error: {e}", "es_error", status=500)
    result = format_response(response, params, index_name, fields_dict, s, connection)
    return _finalize_oqo_response(result, oqo, MessageSchema)


def _oql_parse_error_response(exc: OQLParseError):
    """Structured 400 for an OQL parse failure, surfacing per-error position +
    context (oxjob #373, minimal hints — richer named diagnostics are #357's)."""
    errors = []
    for pe in (exc.errors or []):
        errors.append(
            {
                "type": "parse_error",
                "message": pe.message,
                "position": pe.position,
                "context": pe.context,
                "location": None,
            }
        )
    if not errors:
        errors.append(
            {
                "type": "parse_error",
                "message": str(exc),
                "position": None,
                "context": None,
                "location": None,
            }
        )
    return jsonify(
        {"validation": {"valid": False, "errors": errors, "warnings": []}}
    ), 400


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


def _effective_corpus(oqo, connection):
    """The corpus constraint to enforce for this execution: "core", "expansion",
    or None for no is_xpac constraint. Shared by the normal and semantic paths
    so their precedence can't diverge.

    Only works-on-walden has a corpus split (#481). Precedence (transitional
    back-compat): an explicit is_xpac filter still in the OQO wins (legacy
    escape hatch — inject nothing); else a non-default `corpus`; else the legacy
    `include_xpac=true` URL param maps to "all" until #464 drops it; else "core".
    "all" (core + expansion) needs no constraint, so it also returns None.
    """
    if oqo.get_rows != "works" or connection != "walden":
        return None
    if _oqo_mentions_column(oqo.filter_rows, "is_xpac"):
        return None
    if oqo.corpus and oqo.corpus != "core":
        corpus = oqo.corpus
    elif (
        request.args.get("include_xpac") == "true"
        or request.args.get("include-xpac") == "true"
    ):
        corpus = "all"
    else:
        corpus = "core"
    return corpus if corpus in ("core", "expansion") else None


def _set_size(params, s):
    if params["group_by"]:
        return s.extra(size=0, track_total_hits=True)
    return s.extra(size=params["per_page"], track_total_hits=True)


def _set_cursor_pagination(params, s):
    if not params["group_by"]:
        return handle_cursor(params["cursor"], params["page"], s)
    return s
