"""
Semantic Search using Elasticsearch kNN with pre-filtering.

TEMPORARY SHIM: This module implements semantic search triggered by the
`semantic=true` query parameter. This is a temporary API signature to enable
testing while we work on the full implementation.

Long-term plan: Replace `?search=query&semantic=true` with a proper
`filter=search.semantic:query` syntax that integrates naturally with the
existing filter system.

Usage:
    GET /works?search=machine+learning&semantic=true
    GET /works?search=climate+change&semantic=true&filter=is_oa:true

The semantic search:
1. Embeds the search query using Databricks GTE model (1024 dims)
2. Runs kNN search against the vector_embedding field in works-v31
3. Applies any filters as pre-filters (filter BEFORE vector search)
4. Returns results ranked by vector similarity score
"""

import time
import requests as http_requests

from elasticsearch_dsl import Search, connections

import settings
from core.exceptions import APIQueryParamsError
from core.knn import KNNQueryWithFilter
from core.utils import get_field

# Databricks embedding model config
EMBEDDING_MODEL = "databricks-gte-large-en"
EMBEDDING_DIMENSION = 1024
VECTOR_FIELD = "vector_embedding"

# kNN search parameters
DEFAULT_K = 25
DEFAULT_NUM_CANDIDATES = 100


def embed_query(query_text: str) -> list:
    """
    Embed query text using Databricks GTE model via Foundation Model API.

    Uses direct REST API call to model serving endpoint for low latency
    (typically <200ms vs 1-2s via SQL warehouse).

    Args:
        query_text: Text to embed (will be truncated to 2000 chars)

    Returns:
        List of floats (1024-dimensional embedding)

    Raises:
        APIQueryParamsError: If embedding fails
    """
    if not query_text or not query_text.strip():
        raise APIQueryParamsError("Search query is required for semantic search")

    # Truncate to stay within model limits
    truncated = query_text[:2000]

    host = settings.DATABRICKS_HOST
    token = settings.DATABRICKS_TOKEN

    if not host or not token:
        raise APIQueryParamsError("Semantic search is not configured")

    host = host.replace("https://", "").replace("http://", "")
    url = f"https://{host}/serving-endpoints/{EMBEDDING_MODEL}/invocations"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"input": truncated}

    try:
        response = http_requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        embedding = result["data"][0]["embedding"]
        return [float(x) for x in embedding]
    except Exception as e:
        raise APIQueryParamsError(f"Failed to embed query: {str(e)}")


def build_filter_dict(fields_dict, filter_params) -> dict:
    """
    Build an ES filter dict from parsed filter parameters.

    This converts the filter parsing logic to produce a dict suitable
    for use as a kNN pre-filter.

    Args:
        fields_dict: Field definitions for the entity type
        filter_params: Parsed filter parameters (list of dicts)

    Returns:
        ES filter dict (bool query with must clauses)
    """
    if not filter_params:
        return None

    # Build a temporary Search object to collect filters
    # This reuses the existing filter logic
    temp_search = Search()

    for filter_item in filter_params:
        for key, value in filter_item.items():
            # Skip special params
            if key in ('include_xpac', 'include-xpac'):
                continue

            field = get_field(fields_dict, key)

            # Handle simple filters (no OR/AND complexity for now)
            # TODO: Support full filter syntax for semantic search
            if "|" not in value and " " not in value:
                field.value = value
                q = field.build_query()
                temp_search = temp_search.filter(q)

    # Extract the filter from the Search object
    search_dict = temp_search.to_dict()
    if 'query' in search_dict:
        return search_dict['query']

    return None


def semantic_search_works(
    query_text: str,
    filter_params: list = None,
    fields_dict: dict = None,
    per_page: int = 25,
    index_name: str = None,
    connection: str = 'walden'
) -> dict:
    """
    Perform semantic search on works using ES kNN with pre-filtering.

    TEMPORARY SHIM: This function is triggered by `semantic=true` parameter.
    Long-term, this should integrate with the standard filter system.

    Args:
        query_text: The search query to embed
        filter_params: Parsed filter parameters for pre-filtering
        fields_dict: Field definitions for works
        per_page: Number of results to return
        index_name: ES index name (defaults to works-v31)
        connection: ES connection name

    Returns:
        Dict with meta and results matching the standard API format
    """
    timing = {}
    total_start = time.time()

    # Default index
    if index_name is None:
        index_name = settings.WORKS_INDEX_WALDEN

    # Step 1: Embed the query
    t0 = time.time()
    query_vector = embed_query(query_text)
    timing["embed_ms"] = round((time.time() - t0) * 1000)

    # Step 2: Build pre-filter (if any)
    filter_dict = None
    if filter_params and fields_dict:
        filter_dict = build_filter_dict(fields_dict, filter_params)

    # Step 3: Build kNN query
    knn = KNNQueryWithFilter(
        field=VECTOR_FIELD,
        query_vector=query_vector,
        k=per_page,
        num_candidates=max(per_page * 4, DEFAULT_NUM_CANDIDATES),
        filter_query=filter_dict
    )

    # Step 4: Execute kNN search directly via ES client
    t0 = time.time()
    es = connections.get_connection(connection)

    # Build the search body with kNN at top level
    search_body = {
        "knn": knn.to_dict(),
        "_source": {
            "excludes": ["abstract", "embeddings", "fulltext", "authorships_full", "vector_embedding"]
        },
        "size": per_page
    }

    response = es.search(index=index_name, body=search_body)
    timing["search_ms"] = round((time.time() - t0) * 1000)

    # Step 5: Format results
    t0 = time.time()
    # Import here to avoid circular import (works.views imports this module)
    from works.schemas import WorksSchema
    works_schema = WorksSchema()
    results = []

    for hit in response['hits']['hits']:
        # Convert ES hit to schema-compatible format
        work_data = hit['_source']
        work_data['meta'] = {'score': hit['_score']}

        serialized = works_schema.dump(work_data)
        # Add score to the result
        serialized['relevance_score'] = round(hit['_score'], 4)
        results.append(serialized)

    timing["serialize_ms"] = round((time.time() - t0) * 1000)
    timing["total_ms"] = round((time.time() - total_start) * 1000)

    return {
        "meta": {
            "count": len(results),
            "per_page": per_page,
            "page": 1,
            "semantic_search": True,  # Flag to indicate semantic search was used
            "timing": timing
        },
        "results": results
    }
