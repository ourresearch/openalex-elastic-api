"""
Two-phase semantic search using dedicated vector index.

Phase 1: kNN on works-vectors-v1 (lightweight: 12 shards, 14 filter fields)
Phase 2: mget full docs from works-v32, merge scores, citation rescore

This replaces single-index kNN on works-v32 (72 shards, HNSW can't stay warm).
"""

import logging
import math
from collections import OrderedDict

from elasticsearch_dsl import connections

import settings
from core.exceptions import APIQueryParamsError
from core.semantic_search import embed_query, VECTOR_FIELD
from core.utils import get_full_openalex_id

logger = logging.getLogger(__name__)

# Maps API filter param names to vector index field names.
# These are the only filters supported for semantic search.
#
# DISABLED FILTERS (data exists in index but excluded for performance):
#   "authorships.institutions.country_code" → "country_codes"
#       Matches millions of docs; kNN pre-filter scan across 96 segments/shard
#       takes 15-20s, which ties up a Heroku dyno and blocks other requests.
#   "cited_by_count" → "cited_by_count"
#       Range queries (e.g. >100) match millions of docs; same timeout issue.
#       Exact match works but is rarely useful. Disabled for consistency.
FILTER_FIELD_MAP = {
    "publication_year": "publication_year",
    "type": "type",
    "is_oa": "is_oa",
    "open_access.is_oa": "is_oa",
    "language": "language",
    "authorships.author.id": "author_ids",
    "author.id": "author_ids",
    "authorships.institutions.id": "institution_ids",
    "institution.id": "institution_ids",
    "institutions.id": "institution_ids",
    # "authorships.institutions.country_code": "country_codes",  # DISABLED: broad filter, 15-20s kNN timeout
    "is_retracted": "is_retracted",
    "primary_location.source.id": "source_id",
    # "cited_by_count": "cited_by_count",  # DISABLED: range queries too slow for kNN pre-filter
    "funders.id": "funder_ids",
    "has_fulltext": "has_fulltext",
    "has_abstract": "has_abstract",
    "primary_location.license": "license_id",
}

SUPPORTED_VECTOR_FILTERS = set(FILTER_FIELD_MAP.keys())

# Fields that are boolean in the vector index
_BOOLEAN_FIELDS = {"is_oa", "open_access.is_oa", "is_retracted", "has_fulltext", "has_abstract"}

# Fields that support range queries (integer)
# NOTE: cited_by_count removed — range queries on broad fields cause kNN timeouts
_RANGE_FIELDS = {"publication_year"}

# Fields that contain OpenAlex IDs (need normalization to full URLs)
_ID_FIELDS = {
    "authorships.author.id", "author.id",
    "authorships.institutions.id", "institution.id", "institutions.id",
    "primary_location.source.id", "funders.id",
}

# Non-ID keyword fields where values must be lowercased to match indexed data.
# (In works-v32, the .lower subfield handles case-insensitivity automatically;
# the vector index stores lowercase values and uses plain keyword type.)
# NOTE: country_code removed — disabled as a supported filter
_LOWERCASE_FIELDS = {"type", "language"}

# Fields that store license values as full URLs (e.g., "https://openalex.org/licenses/cc-by")
_LICENSE_FIELDS = {"primary_location.license"}

# Filter keys that are search operations (incompatible with semantic search)
_SEARCH_FILTER_KEYS = {
    "abstract.search", "default.search", "display_name.search",
    "fulltext.search", "keyword.search", "raw_affiliation_strings.search",
    "raw_author_name.search", "title.search",
    "title_and_abstract.search",
}


# Max results for semantic search (kNN returns at most this many candidates)
MAX_SEMANTIC_RESULTS = 50


def validate_vector_filters(params):
    """Check that all filter params are supported on the vector index.

    Raises APIQueryParamsError if any unsupported filter is found, or if
    search-type filters are combined with semantic search.
    """
    if not params.get("filters"):
        return

    for f in params["filters"]:
        for key in f:
            if key in _SEARCH_FILTER_KEYS or key.endswith(".search"):
                raise APIQueryParamsError(
                    f"Cannot combine search.semantic with filter={key}. "
                    "Use only one search method per request."
                )
            if key not in SUPPORTED_VECTOR_FILTERS:
                supported_list = ", ".join(sorted(SUPPORTED_VECTOR_FILTERS))
                raise APIQueryParamsError(
                    f"Filter '{key}' is not supported with semantic search. "
                    f"Supported filters: {supported_list}"
                )


def build_vector_filter(params):
    """Build ES filter dict from params for kNN pre-filtering on the vector index.

    Returns None if no filters, otherwise a bool/must filter dict.
    Handles:
    - Boolean fields: term query with true/false
    - Range fields: range query with gt/gte/lt/lte operators or exact match
    - Keyword fields: term query (single value) or terms query (pipe-separated OR)
    - Negation: !value → must_not
    """
    if not params.get("filters"):
        return None

    must = []
    must_not = []

    for filter_dict in params["filters"]:
        for key, value in filter_dict.items():
            if key not in FILTER_FIELD_MAP:
                continue

            field_name = FILTER_FIELD_MAP[key]

            # Handle negation
            negate = False
            if isinstance(value, str) and value.startswith("!"):
                negate = True
                value = value[1:]

            clause = _build_single_filter(key, field_name, value)
            if clause:
                if negate:
                    must_not.append(clause)
                else:
                    must.append(clause)

    if not must and not must_not:
        return None

    bool_query = {}
    if must:
        bool_query["must"] = must
    if must_not:
        bool_query["must_not"] = must_not

    return {"bool": bool_query}


def _build_single_filter(key, field_name, value):
    """Build a single ES filter clause for one key-value pair."""
    if key in _BOOLEAN_FIELDS:
        bool_val = str(value).lower() in ("true", "1", "yes")
        return {"term": {field_name: bool_val}}

    if key in _RANGE_FIELDS:
        return _build_range_filter(field_name, value)

    # Keyword fields — handle OR (pipe-separated) values
    # Normalize OpenAlex IDs to full URLs (e.g., "S1980519" → "https://openalex.org/S1980519")
    # Normalize license values to full URLs (e.g., "cc-by" → "https://openalex.org/licenses/cc-by")
    # Lowercase non-ID keyword fields to match indexed data (vector index has no .lower subfield)
    if "|" in str(value):
        values = [v.strip() for v in str(value).split("|") if v.strip()]
        if key in _ID_FIELDS:
            values = [get_full_openalex_id(v) or v for v in values]
        elif key in _LICENSE_FIELDS:
            values = [_normalize_license(v) for v in values]
        elif key in _LOWERCASE_FIELDS:
            values = [v.lower() for v in values]
        return {"terms": {field_name: values}}

    str_value = str(value)
    if key in _ID_FIELDS:
        str_value = get_full_openalex_id(str_value) or str_value
    elif key in _LICENSE_FIELDS:
        str_value = _normalize_license(str_value)
    elif key in _LOWERCASE_FIELDS:
        str_value = str_value.lower()
    return {"term": {field_name: str_value}}


def _build_range_filter(field_name, value):
    """Build a range or term filter for integer fields.

    Supports: >N, <N, >=N, <=N, N-M (range), plain N (exact match).
    """
    value = str(value).strip()

    if value.startswith(">="):
        return {"range": {field_name: {"gte": int(value[2:])}}}
    if value.startswith("<="):
        return {"range": {field_name: {"lte": int(value[2:])}}}
    if value.startswith(">"):
        return {"range": {field_name: {"gt": int(value[1:])}}}
    if value.startswith("<"):
        return {"range": {field_name: {"lt": int(value[1:])}}}
    if "-" in value and not value.startswith("-"):
        parts = value.split("-", 1)
        return {"range": {field_name: {"gte": int(parts[0]), "lte": int(parts[1])}}}

    # Exact match
    return {"term": {field_name: int(value)}}


def _normalize_license(value):
    """Normalize license value to full OpenAlex URL if needed."""
    if value.startswith("https://"):
        return value
    return f"https://openalex.org/licenses/{value}"


def execute_vector_search(query_vector, filter_dict, k=50, num_candidates=75):
    """Run kNN search on works-vectors-v1.

    Returns list of (work_id, score) tuples sorted by score descending.
    """
    es = connections.get_connection("walden")

    knn_body = {
        "field": VECTOR_FIELD,
        "query_vector": query_vector,
        "k": k,
        "num_candidates": num_candidates,
        "similarity": 0.5,
    }
    if filter_dict:
        knn_body["filter"] = filter_dict

    body = {
        "knn": knn_body,
        "_source": False,
        "fields": ["cited_by_count"],
        "size": k,
    }

    response = es.search(index=settings.WORKS_VECTOR_INDEX, body=body)

    results = []
    for hit in response["hits"]["hits"]:
        work_id = hit["_id"]
        score = hit["_score"]
        cited_by = 0
        if "fields" in hit and "cited_by_count" in hit["fields"]:
            cited_by = hit["fields"]["cited_by_count"][0] or 0
        results.append((work_id, score, cited_by))

    return results


# Maps vector index field names to works-v33 field names (only where they differ).
# Vector index uses flat field names; works-v33 uses nested paths and .lower subfields.
_VECTOR_TO_WORKS_FIELD = {
    "is_oa": "open_access.is_oa",
    "source_id": "primary_location.source.id",
    "author_ids": "authorships.author.id",
    "institution_ids": "authorships.institutions.id",
    "funder_ids": "funders.id",
    "license_id": "primary_location.license",
    "type": "type.lower",
    "language": "language.lower",
}


def _translate_filter_for_works(filter_dict):
    """Translate a vector-index filter dict to use works-v33 field names."""
    if not filter_dict:
        return None

    def _translate_clause(clause):
        for query_type in ("term", "terms", "range"):
            if query_type in clause:
                field = next(iter(clause[query_type]))
                new_field = _VECTOR_TO_WORKS_FIELD.get(field, field)
                return {query_type: {new_field: clause[query_type][field]}}
        return clause

    result = {"bool": {}}
    for key in ("must", "must_not"):
        if key in filter_dict.get("bool", {}):
            result["bool"][key] = [
                _translate_clause(c) for c in filter_dict["bool"][key]
            ]
    return result if result["bool"] else None


def _text_boost_search(query_text, k=20, connection="walden", filter_dict=None):
    """Fetch top-cited works matching query text from works-v33.

    Used to inject highly cited candidates into the kNN pool for short queries,
    where embedding geometry bias causes generic low-citation works to dominate.

    Returns list of (work_id, synthetic_knn_score, cited_by_count) tuples.
    """
    es = connections.get_connection(connection)

    match_query = {
        "match": {
            "display_name": {
                "query": query_text,
                "operator": "and",
            }
        }
    }

    # Apply user filters translated to works-v33 field names
    works_filter = _translate_filter_for_works(filter_dict)
    if works_filter:
        query = {
            "bool": {
                "must": [match_query],
                "filter": [works_filter],
            }
        }
    else:
        query = match_query

    body = {
        "query": query,
        "sort": [{"cited_by_count": {"order": "desc"}}],
        "_source": False,
        "fields": ["cited_by_count"],
        "size": k,
    }

    response = es.search(index=settings.WORKS_INDEX_WALDEN, body=body)

    results = []
    for hit in response["hits"]["hits"]:
        work_id = hit["_id"]
        cited_by = 0
        if "fields" in hit and "cited_by_count" in hit["fields"]:
            cited_by = hit["fields"]["cited_by_count"][0] or 0
        # Synthetic kNN score just above the similarity threshold
        results.append((work_id, 0.55, cited_by))

    return results


def hydrate_results(vector_results, connection="walden"):
    """Fetch full work docs from works-v32 via mget, merge scores.

    Args:
        vector_results: list of (work_id, knn_score, cited_by_count) tuples
        connection: ES connection name

    Returns:
        List of ES hit-like dicts with _source and injected meta.score
    """
    if not vector_results:
        return []

    es = connections.get_connection(connection)
    work_ids = [r[0] for r in vector_results]

    # Build score map with citation rescore.
    #
    # We use a saturation function with a relevance gate to combine kNN
    # similarity with citation count. The goal: citations should act as a
    # tiebreaker among similarly-relevant results, not override relevance.
    #
    # Formula:
    #   citation_signal = cited_by / (cited_by + PIVOT)        — bounded 0..1 (saturation)
    #   relevance_strength = (knn - FLOOR) / (1 - FLOOR)       — 0 at threshold, 1 at perfect match
    #   citation_factor = 1 + MAX_BOOST * relevance_strength * citation_signal
    #   final_score = knn_score * citation_factor
    #
    # Why saturation (not log):
    #   log(cited_by) is unbounded and steep at low values — a 45-cite paper
    #   gets a 4.8x boost, enough to outrank a more-relevant 5-cite paper.
    #   Saturation is bounded (max boost = 1 + MAX_BOOST) and flattens out,
    #   so 10K cites isn't much different from 1K.
    #
    # Why relevance-gated:
    #   Without the gate, a low-relevance/high-citation result can leapfrog a
    #   high-relevance/low-citation one. The gate scales citation influence by
    #   how far above the similarity floor the kNN score is. A result barely
    #   above threshold gets almost no citation boost regardless of cite count.
    #
    # Tuning (all env vars, no deploy needed):
    #   CITATION_PIVOT (default 100) — citation count that gives 50% of max boost.
    #       Lower = citations matter sooner. Higher = only blockbuster papers get boosted.
    #   CITATION_MAX_BOOST (default 0.5) — max multiplicative boost from citations.
    #       0.5 means a maximally-cited, maximally-relevant paper scores 1.5x its kNN score.
    #   CITATION_KNN_FLOOR (default 0.5) — kNN similarity threshold (matches ES kNN similarity param).
    #       Results at this score get zero citation boost.
    #
    # Previous formula was: `knn_score * (1 + ln(cited_by))` with a 0.5x penalty
    # for uncited works. That gave a 45-cite paper a 9.6x advantage over uncited,
    # causing ranking failures like chess papers outranking boxing papers.
    pivot = settings.CITATION_PIVOT
    max_boost = settings.CITATION_MAX_BOOST
    knn_floor = settings.CITATION_KNN_FLOOR

    score_map = {}
    for work_id, knn_score, cited_by in vector_results:
        citation_signal = cited_by / (cited_by + pivot) if cited_by > 0 else 0.0
        relevance_strength = max(0.0, min(1.0, (knn_score - knn_floor) / (1.0 - knn_floor)))
        citation_factor = 1.0 + max_boost * relevance_strength * citation_signal
        score_map[work_id] = knn_score * citation_factor

    # mget full docs from works-v32
    response = es.mget(
        index=settings.WORKS_INDEX_WALDEN,
        body={"ids": work_ids},
        _source_excludes=["abstract", "embeddings", "fulltext", "authorships_full", "vector_embedding"],
    )

    # Build hit objects that work with WorksSchema serialization
    hits = []
    for doc in response["docs"]:
        if not doc.get("found"):
            continue
        hit = doc["_source"]
        hit["_id"] = doc["_id"]
        hit["_score"] = score_map.get(doc["_id"], 0)
        hits.append(hit)

    # Sort by rescored score (descending)
    hits.sort(key=lambda h: h.get("_score", 0), reverse=True)

    return hits


def vector_semantic_search(params, index_name, connection):
    """Execute two-phase semantic search and return formatted result.

    This is the main entry point, called from shared_view when USE_VECTOR_INDEX
    is enabled and the search type is semantic.
    """
    # Reject group_by with semantic search on vector index
    if params.get("group_by") or params.get("group_bys"):
        raise APIQueryParamsError(
            "group_by is not supported with semantic search. "
            "Use group_by with regular search instead."
        )

    # Reject cursor pagination (not supported for semantic search)
    if params.get("cursor"):
        raise APIQueryParamsError(
            "Cursor pagination is not supported with semantic search. "
            "Use page/per_page pagination instead (max 50 results)."
        )

    # Cap per_page for semantic search
    per_page = params.get("per_page", 25) or 25
    if per_page > MAX_SEMANTIC_RESULTS:
        raise APIQueryParamsError(
            f"per_page cannot exceed {MAX_SEMANTIC_RESULTS} for semantic search. "
            f"Received per_page={per_page}."
        )

    # Strip is_xpac default filter — vector index only contains non-xpac works
    if params.get("filters"):
        params["filters"] = [
            f for f in params["filters"] if "is_xpac" not in f
        ]

    # Validate filters
    validate_vector_filters(params)

    import time
    t0 = time.time()

    try:
        # Embed query
        query_vector = embed_query(params["search"])

        # Build filter
        filter_dict = build_vector_filter(params)
    except Exception:
        import traceback; print(f"VECTOR_ERR embed/filter: {traceback.format_exc()}", flush=True)
        raise

    # Execute kNN on vector index
    k = MAX_SEMANTIC_RESULTS
    num_candidates = max(k * 4, 200)
    try:
        vector_results = execute_vector_search(query_vector, filter_dict, k=k, num_candidates=num_candidates)
    except Exception:
        import traceback; print(f"VECTOR_ERR kNN filter={filter_dict}: {type(e).__name__}: {e}", flush=True)
        raise

    # Text-boost injection for short queries (≤ 3 words)
    if settings.SEMANTIC_TEXT_BOOST and len(params["search"].split()) <= 3:
        try:
            text_boost_results = _text_boost_search(params["search"], k=20, connection=connection, filter_dict=filter_dict)
            existing_ids = {r[0] for r in vector_results}
            for result in text_boost_results:
                if result[0] not in existing_ids:
                    vector_results.append(result)
                    existing_ids.add(result[0])
        except Exception:
            import traceback; print(f"VECTOR_ERR text_boost: {traceback.format_exc()}", flush=True)
            # Non-fatal: continue with kNN results only

    # Hydrate full docs from works-v33
    try:
        hits = hydrate_results(vector_results, connection)
    except Exception:
        import traceback; print(f"VECTOR_ERR hydrate: {type(e).__name__}: {e}", flush=True)
        raise

    db_response_time_ms = int((time.time() - t0) * 1000)

    # Paginate
    page = params.get("page", 1) or 1
    start = (page - 1) * per_page
    end = start + per_page
    page_hits = hits[start:end]

    # Convert raw dicts to hit-like objects for WorksSchema
    from elasticsearch_dsl.utils import AttrDict
    result_objects = []
    for hit in page_hits:
        score = hit.pop("_score", 0)
        obj = AttrDict(hit)
        obj.meta = AttrDict({"score": score, "id": hit.get("_id", hit.get("id", ""))})
        result_objects.append(obj)

    # Build response in same format as shared_view
    result = OrderedDict()
    result["meta"] = {
        "count": len(hits),
        "db_response_time_ms": db_response_time_ms,
        "page": page,
        "per_page": per_page,
        "groups_count": None,
    }
    result["group_by"] = []
    result["results"] = result_objects

    return result
