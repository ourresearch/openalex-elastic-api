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
import json

from elasticsearch_dsl import Q, Search
from flask import jsonify, request

from core.cursor import handle_cursor
from core.exceptions import APIError, APIQueryParamsError
from core.paginate import get_per_page
from core.preference import clean_preference, combine_preferences
from core.shared_view import (
    apply_grouping,
    apply_sorting,
    execute_search,
    format_response,
    set_source,
)
from core.utils import get_data_version_connection
from query_translation.oqo import OQO, VALID_OPERATORS
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.oqo_to_es import (
    OQOTranslationError,
    oqo_to_search_and_filter_q,
)
from query_translation.oql_parser import OQLParseError, parse_oql_to_oqo
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.url_renderer import URLRenderError, render_oqo_to_url
from query_translation.validator import validate_oqo, _has_search_clause

# Shared response/render helpers live with the translation resource; execution
# reuses them (no cycle — views.py never imports this module).
from query_translation.views import (
    safe_get_display_name,
    _components_to_oxurl,
    _error_response,
)

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
    return _execute_oqo(oqo.to_dict())


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
    # Attach the private `meta.x_query` triple {oql, oqo, url} so clients can
    # confirm what we executed and rehydrate from it (#373). Injected here, after
    # marshmallow `.dump()` (which would drop an unknown `meta` key), and only on
    # this execute path — keeps `x_query` off `/works?filter=` and out of
    # `/properties`/docs. Replaces #372's top-level `oqo` echo (single canonical
    # home; no other consumer reads the echo — the GUI uses `/query/*`).
    serialized.setdefault("meta", {})["x_query"] = _build_x_query(oqo)
    return jsonify(serialized), 200


def _build_x_query(oqo: OQO) -> dict:
    """Build the private `meta.x_query` triple {oql, oqo, url} (oxjob #373).

    The canonical multi-form representation of the executed query:
      - oql: re-rendered canonical OQL (round-trips: re-parsing it yields `oqo`)
      - oqo: the canonical structured query object the client hydrates from
      - url: the OXURL (`/works?filter=…`) form, or None when the OQO isn't
             URL-expressible (nested boolean trees, multi-dim group_by) — the URL
             syntax is a lossy subset of OQO, so this is null, never a 500.

    `x_query` is deliberately **private/unstable**: `x_` prefix, undocumented,
    injected onto the serialized `meta` AFTER marshmallow `.dump()` (so it never
    needs a schema field) and only on the OQL/OQO execute path — it stays out of
    `/properties` and the public docs.
    """
    canonical = canonicalize_oqo(oqo)

    url_form = None
    try:
        components = render_oqo_to_url(canonical)
        url_form = _components_to_oxurl(canonical.get_rows, components)
    except URLRenderError:
        # Not URL-expressible (e.g. nested boolean tree). url stays None; the
        # client treats null as an "advanced query" it can't render as chips.
        pass

    return {
        # Resolve ES-backed entity display names (institution/author/source/…)
        # so the SERP's x_query.oql reads `institution is I136199984 [Harvard]`,
        # not a bare ID (#376 readability). Mirrors the /query/oql translate path;
        # safe_get_display_name caches + swallows lookup errors, and countries /
        # languages / SDGs still resolve via the built-in tables.
        "oql": render_oqo_to_oql(canonical, entity_resolver=safe_get_display_name),
        "oqo": canonical.to_dict(),
        "url": url_form,
    }


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
