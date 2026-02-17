"""
Two-phase semantic search using dedicated vector index.

Phase 1: kNN on works-vectors-v1 (lightweight: 12 shards, 14 filter fields)
Phase 2: mget full docs from works-v32, merge scores, citation rescore

This replaces single-index kNN on works-v32 (72 shards, HNSW can't stay warm).
"""

import math
from collections import OrderedDict

from elasticsearch_dsl import connections

import settings
from core.exceptions import APIQueryParamsError
from core.semantic_search import embed_query, VECTOR_FIELD
from core.utils import get_full_openalex_id

# Maps API filter param names to vector index field names.
# These are the only filters supported for semantic search.
FILTER_FIELD_MAP = {
    "publication_year": "publication_year",
    "type": "type",
    "is_oa": "is_oa",
    "language": "language",
    "authorships.author.id": "author_ids",
    "authorships.institutions.id": "institution_ids",
    "authorships.institutions.country_code": "country_codes",
    "is_retracted": "is_retracted",
    "primary_location.source.id": "source_id",
    "cited_by_count": "cited_by_count",
    "funders.id": "funder_ids",
    "has_fulltext": "has_fulltext",
    "has_abstract": "has_abstract",
    "primary_location.license": "license_id",
}

SUPPORTED_VECTOR_FILTERS = set(FILTER_FIELD_MAP.keys())

# Fields that are boolean in the vector index
_BOOLEAN_FIELDS = {"is_oa", "is_retracted", "has_fulltext", "has_abstract"}

# Fields that support range queries (integer)
_RANGE_FIELDS = {"publication_year", "cited_by_count"}

# Fields that contain OpenAlex IDs (need normalization to full URLs)
_ID_FIELDS = {
    "authorships.author.id", "authorships.institutions.id",
    "primary_location.source.id", "funders.id",
}

# Non-ID keyword fields where values must be lowercased to match indexed data.
# (In works-v32, the .lower subfield handles case-insensitivity automatically;
# the vector index stores lowercase values and uses plain keyword type.)
_LOWERCASE_FIELDS = {"type", "language", "authorships.institutions.country_code"}

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
    # Lowercase non-ID keyword fields to match indexed data (vector index has no .lower subfield)
    if "|" in str(value):
        values = [v.strip() for v in str(value).split("|") if v.strip()]
        if key in _ID_FIELDS:
            values = [get_full_openalex_id(v) or v for v in values]
        elif key in _LOWERCASE_FIELDS:
            values = [v.lower() for v in values]
        return {"terms": {field_name: values}}

    str_value = str(value)
    if key in _ID_FIELDS:
        str_value = get_full_openalex_id(str_value) or str_value
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

    # Build score map with citation rescore
    score_map = {}
    for work_id, knn_score, cited_by in vector_results:
        if cited_by <= 1:
            citation_factor = 0.5
        else:
            citation_factor = 1 + math.log(cited_by)
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

    # Validate filters
    validate_vector_filters(params)

    # Embed query
    query_vector = embed_query(params["search"])

    # Build filter
    filter_dict = build_vector_filter(params)

    # Execute kNN on vector index
    k = MAX_SEMANTIC_RESULTS
    num_candidates = max(k * 2, 75)
    vector_results = execute_vector_search(query_vector, filter_dict, k=k, num_candidates=num_candidates)

    # Hydrate full docs from works-v32
    hits = hydrate_results(vector_results, connection)

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
        "db_response_time_ms": 0,
        "page": page,
        "per_page": per_page,
        "groups_count": None,
    }
    result["group_by"] = []
    result["results"] = result_objects

    return result
