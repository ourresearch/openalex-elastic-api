"""
Vector Search endpoint for semantic similarity search over OpenAlex works.

Endpoint: /find/works
Cost: 1000 credits per query

Flow:
1. Embed query text using OpenAI text-embedding-3-small
2. Search Databricks Mosaic AI Vector Search for similar work IDs
3. Hydrate results from Elasticsearch
4. Return full work objects with similarity scores
"""

from flask import Blueprint, jsonify, request
from openai import OpenAI
from databricks.vector_search.client import VectorSearchClient
from elasticsearch_dsl import Search, Q, connections

import settings
from core.exceptions import APIQueryParamsError
from works.schemas import WorksSchema

blueprint = Blueprint("vector_search", __name__)

# Configuration
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SEARCH_ENDPOINT = "openalex-vector-search"
VECTOR_SEARCH_INDEX = "openalex.vector_search.work_embeddings_index"
DEFAULT_PER_PAGE = 100
MAX_PER_PAGE = 100
WORKS_INDEX = settings.WORKS_INDEX_WALDEN


def get_openai_client():
    """Get OpenAI client."""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise APIQueryParamsError("OpenAI API key not configured")
    return OpenAI(api_key=api_key)


def get_vector_search_client():
    """Get Databricks Vector Search client using PAT token."""
    host = settings.DATABRICKS_HOST
    token = settings.DATABRICKS_TOKEN
    if not host or not token:
        raise APIQueryParamsError("Databricks not configured")

    host = host.replace("https://", "").replace("http://", "")

    return VectorSearchClient(
        workspace_url=f"https://{host}",
        personal_access_token=token
    )


def embed_query(text: str) -> list:
    """
    Embed query text using OpenAI text-embedding-3-small.

    Args:
        text: Query text to embed

    Returns:
        List of floats (1536 dimensions)
    """
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def build_filter_dict(filters: dict) -> dict:
    """
    Build filter dict for VectorSearchClient.

    The SDK uses a dict format like:
    {"column_name op": value} where op is one of: <, <=, >, >=, =, !=, LIKE, NOT LIKE

    Args:
        filters: Dict with publication_year, type, is_oa keys

    Returns:
        Dict suitable for VectorSearchClient filters parameter
    """
    if not filters:
        return None

    filter_dict = {}

    if "publication_year" in filters:
        year_filter = str(filters["publication_year"])
        if year_filter.startswith(">="):
            filter_dict["publication_year >="] = int(year_filter[2:])
        elif year_filter.startswith("<="):
            filter_dict["publication_year <="] = int(year_filter[2:])
        elif year_filter.startswith(">"):
            filter_dict["publication_year >"] = int(year_filter[1:])
        elif year_filter.startswith("<"):
            filter_dict["publication_year <"] = int(year_filter[1:])
        elif "-" in year_filter:
            start, end = year_filter.split("-")
            filter_dict["publication_year >="] = int(start)
            filter_dict["publication_year <="] = int(end)
        else:
            filter_dict["publication_year"] = int(year_filter)

    if "type" in filters:
        filter_dict["type"] = filters["type"]

    if "is_oa" in filters:
        is_oa_val = str(filters["is_oa"]).lower() == "true"
        filter_dict["is_oa"] = is_oa_val

    if "has_abstract" in filters:
        has_abstract_val = str(filters["has_abstract"]).lower() == "true"
        filter_dict["has_abstract"] = has_abstract_val

    return filter_dict if filter_dict else None


def search_vectors(
    query_embedding: list,
    num_results: int = 10,
    filters: dict = None
) -> list:
    """
    Search Databricks Vector Search for similar works.

    Args:
        query_embedding: Query vector (1536 dimensions)
        num_results: Number of results to return
        filters: Optional metadata filters (publication_year, type, is_oa, has_abstract)

    Returns:
        List of dicts with work_id and score
    """
    vsc = get_vector_search_client()
    index = vsc.get_index(VECTOR_SEARCH_ENDPOINT, VECTOR_SEARCH_INDEX)

    # Build filter dict
    filter_dict = build_filter_dict(filters)

    # Perform similarity search
    results = index.similarity_search(
        query_vector=query_embedding,
        num_results=num_results,
        columns=["work_id"],
        filters=filter_dict
    )

    # Parse results: work_id is first column, score is last column
    data_array = results.get('result', {}).get('data_array', [])
    parsed = [{"work_id": row[0], "score": row[-1]} for row in data_array]
    print(f"[vector_search] search_vectors: got {len(parsed)} results, first 3: {parsed[:3]}")
    return parsed


def hydrate_works(work_ids: list) -> dict:
    """
    Fetch full work objects from Elasticsearch.

    Args:
        work_ids: List of OpenAlex work IDs (integers or strings)

    Returns:
        Dict mapping work_id (integer) to work object
    """
    if not work_ids:
        print(f"[vector_search] hydrate_works: no work_ids provided")
        return {}

    # Convert integer work_ids to OpenAlex URL format for ES query
    openalex_ids = [f"https://openalex.org/W{wid}" for wid in work_ids]
    print(f"[vector_search] hydrate_works: querying {len(openalex_ids)} IDs, first 3: {openalex_ids[:3]}")

    es = connections.get_connection('walden')
    s = Search(index=WORKS_INDEX, using=es)
    print(f"[vector_search] hydrate_works: using index {WORKS_INDEX}")

    # Search by ID
    s = s.query(Q("terms", id=openalex_ids))
    s = s.extra(size=len(work_ids))

    response = s.execute()
    print(f"[vector_search] hydrate_works: ES returned {len(response.hits)} hits")

    # Build lookup dict mapping string work_id to work object
    works = {}
    for hit in response.hits:
        # Extract ID from URL (e.g., "https://openalex.org/W4286979530" -> "4286979530")
        str_id = hit.id.split("/W")[-1]
        works[str_id] = hit.to_dict()

    return works


def parse_filter(filter_str: str) -> dict:
    """
    Parse filter string into dict.

    Supported formats:
    - publication_year:2023
    - publication_year:>2020
    - publication_year:2020-2023
    - type:article
    - is_oa:true

    Returns dict of filter key-value pairs.
    """
    if not filter_str:
        return {}

    filters = {}
    for part in filter_str.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key in ["publication_year", "type", "is_oa", "has_abstract"]:
            filters[key] = value

    return filters


@blueprint.route("/find/works", methods=["GET", "POST"])
def find_works():
    """
    Semantic similarity search over OpenAlex works.

    GET /find/works?query=...&per_page=10&filter=publication_year:>2020

    POST /find/works
    {
        "query": "full text query...",
        "per_page": 10,
        "filter": {
            "publication_year": ">2020",
            "type": "article",
            "is_oa": true
        }
    }

    Returns:
    {
        "meta": {
            "count": 10,
            "query": "..."
        },
        "results": [
            {
                "score": 0.92,
                "work": { ... full work object ... }
            }
        ]
    }
    """
    # Parse request
    if request.method == "POST":
        data = request.get_json() or {}
        query = data.get("query", "").strip()
        per_page = data.get("per_page", DEFAULT_PER_PAGE)
        filters = data.get("filter", {})
        if isinstance(filters, str):
            filters = parse_filter(filters)
    else:
        query = request.args.get("query", "").strip()
        per_page = request.args.get("per_page", DEFAULT_PER_PAGE, type=int)
        filter_str = request.args.get("filter", "")
        filters = parse_filter(filter_str)

    # Validate query
    if not query:
        raise APIQueryParamsError("query parameter is required")

    if len(query) > 10000:
        raise APIQueryParamsError("query must be at most 10,000 characters")

    # Validate per_page
    try:
        per_page = int(per_page)
    except (ValueError, TypeError):
        raise APIQueryParamsError("per_page must be an integer")

    if per_page < 1:
        raise APIQueryParamsError("per_page must be at least 1")
    if per_page > MAX_PER_PAGE:
        raise APIQueryParamsError(f"per_page must be at most {MAX_PER_PAGE}")

    # Step 1: Embed query
    try:
        query_embedding = embed_query(query)
    except Exception as e:
        raise APIQueryParamsError(f"Failed to embed query: {str(e)}")

    # Step 2: Vector search
    try:
        vector_results = search_vectors(
            query_embedding=query_embedding,
            num_results=per_page,
            filters=filters
        )
    except Exception as e:
        raise APIQueryParamsError(f"Vector search failed: {str(e)}")

    # Step 3: Hydrate from Elasticsearch
    work_ids = [r["work_id"] for r in vector_results]
    works = hydrate_works(work_ids)

    # Step 4: Build response
    results = []
    works_schema = WorksSchema()

    for vr in vector_results:
        work_id = vr["work_id"]
        score = vr.get("score", 0.0)
        work_data = works.get(work_id)

        if work_data:
            # Serialize using works schema for consistent output
            serialized_work = works_schema.dump(work_data)
            results.append({
                "score": round(score, 4),
                "work": serialized_work
            })

    return jsonify({
        "meta": {
            "count": len(results),
            "query": query,
            "per_page": per_page,
            "filters_applied": filters if filters else None
        },
        "results": results
    })


@blueprint.route("/find/works/health", methods=["GET"])
def find_works_health():
    """Health check endpoint."""
    checks = {
        "openai": False,
        "databricks": False,
        "elasticsearch": False
    }

    # Check OpenAI
    try:
        client = get_openai_client()
        checks["openai"] = True
    except Exception:
        pass

    # Check Databricks Vector Search
    try:
        vsc = get_vector_search_client()
        index = vsc.get_index(VECTOR_SEARCH_ENDPOINT, VECTOR_SEARCH_INDEX)
        checks["databricks"] = True
    except Exception:
        pass

    # Check Elasticsearch
    try:
        es = connections.get_connection('walden')
        es.info()
        checks["elasticsearch"] = True
    except Exception:
        pass

    all_healthy = all(checks.values())

    return jsonify({
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks
    }), 200 if all_healthy else 503
