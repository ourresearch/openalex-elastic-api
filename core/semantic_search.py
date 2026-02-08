"""
Semantic Search support for Elasticsearch kNN.

Provides query embedding via Databricks GTE model (1024 dims) for use
with the search.semantic parameter on /works.

Usage:
    GET /works?search.semantic=machine+learning+for+drug+discovery
    GET /works?search.semantic=climate+change&filter=is_oa:true
"""

import requests as http_requests

import settings
from core.exceptions import APIQueryParamsError

# Databricks embedding model config
EMBEDDING_MODEL = "databricks-gte-large-en"
EMBEDDING_DIMENSION = 1024
VECTOR_FIELD = "vector_embedding"



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


