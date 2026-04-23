"""
Semantic Search support for Elasticsearch kNN.

Provides query embedding via Databricks GTE model (1024 dims) for use
with the search.semantic parameter on /works.

Usage:
    GET /works?search.semantic=machine+learning+for+drug+discovery
    GET /works?search.semantic=climate+change&filter=is_oa:true
"""

import threading
import time

import requests as http_requests

import settings
from core.exceptions import APIQueryParamsError

# Databricks embedding model config
EMBEDDING_MODEL = "databricks-gte-large-en"
EMBEDDING_DIMENSION = 1024
VECTOR_FIELD = "vector_embedding"

# Refresh OAuth tokens this many seconds before they expire
_TOKEN_REFRESH_BUFFER_SECONDS = 60

_token_lock = threading.Lock()
_cached_access_token = None
_cached_token_expires_at = 0.0


def _get_access_token() -> str:
    global _cached_access_token, _cached_token_expires_at

    now = time.time()
    if _cached_access_token and now < _cached_token_expires_at - _TOKEN_REFRESH_BUFFER_SECONDS:
        return _cached_access_token

    with _token_lock:
        # re-check under lock in case another thread just refreshed
        now = time.time()
        if _cached_access_token and now < _cached_token_expires_at - _TOKEN_REFRESH_BUFFER_SECONDS:
            return _cached_access_token

        client_id = settings.DATABRICKS_OAUTH_CLIENT_ID
        client_secret = settings.DATABRICKS_OAUTH_SECRET
        token_url = settings.DATABRICKS_OAUTH_TOKEN_URL

        if not client_id or not client_secret or not token_url:
            raise APIQueryParamsError("Semantic search is not configured")

        response = http_requests.post(
            token_url,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        _cached_access_token = body["access_token"]
        _cached_token_expires_at = now + float(body.get("expires_in", 3600))
        return _cached_access_token


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
    if not host:
        raise APIQueryParamsError("Semantic search is not configured")

    access_token = _get_access_token()

    host = host.replace("https://", "").replace("http://", "")
    url = f"https://{host}/mlflow/v1/embeddings"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {"model": EMBEDDING_MODEL, "input": truncated}

    try:
        response = http_requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        embedding = result["data"][0]["embedding"]
        return [float(x) for x in embedding]
    except Exception as e:
        raise APIQueryParamsError(f"Failed to embed query: {str(e)}")


