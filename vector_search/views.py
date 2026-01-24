"""
Vector Search endpoint for semantic similarity search over OpenAlex works.

Endpoint: /find/works
Cost: 1000 credits per query

Flow:
1. Embed query text using Databricks GTE model
2. Search Databricks Mosaic AI Vector Search with query vector
3. Hydrate results from Elasticsearch
4. Return full work objects with similarity scores
"""

import time

from flask import Blueprint, jsonify, request
from databricks.vector_search.client import VectorSearchClient
from databricks import sql as databricks_sql
from elasticsearch_dsl import Search, Q, connections

import settings
from core.exceptions import APIQueryParamsError
from works.schemas import WorksSchema

blueprint = Blueprint("vector_search", __name__)

# Configuration
EMBEDDING_MODEL = "databricks-gte-large-en"
EMBEDDING_DIMENSION = 1024
VECTOR_SEARCH_ENDPOINT = "openalex-vector-search"
VECTOR_SEARCH_INDEX = "openalex.vector_search.work_embeddings_index"
DEFAULT_COUNT = 25
MAX_COUNT = 100
WORKS_INDEX = settings.WORKS_INDEX_WALDEN
TOTAL_WORKS_WITH_ABSTRACTS = 217_000_000


def get_vector_search_client():
    """Get Databricks Vector Search client using PAT token."""
    host = settings.DATABRICKS_HOST
    token = settings.DATABRICKS_TOKEN
    if not host or not token:
        raise APIQueryParamsError("Databricks not configured")

    host = host.replace("https://", "").replace("http://", "")

    return VectorSearchClient(
        workspace_url=f"https://{host}",
        personal_access_token=token,
        disable_notice=True
    )


def embed_query(query_text: str) -> list:
    """
    Embed query text using Databricks GTE model via SQL warehouse.

    Args:
        query_text: Text to embed (will be truncated to 2000 chars)

    Returns:
        List of floats (1024-dimensional embedding)
    """
    # Truncate to stay within model limits
    truncated = query_text[:2000]

    # Escape single quotes for SQL
    escaped = truncated.replace("'", "''")

    host = settings.DATABRICKS_HOST.replace("https://", "").replace("http://", "")

    with databricks_sql.connect(
        server_hostname=host,
        http_path=settings.DATABRICKS_HTTP_PATH,
        access_token=settings.DATABRICKS_TOKEN
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT ai_query('{EMBEDDING_MODEL}', '{escaped}')")
            result = cursor.fetchone()
            embedding = result[0]
            # Convert numpy array to list of Python floats if needed
            if hasattr(embedding, 'tolist'):
                return embedding.tolist()
            return [float(x) for x in embedding]


def build_filter_string(filters: dict) -> str:
    """
    Build SQL-style filter string for storage-optimized Vector Search endpoints.

    Storage-optimized endpoints require string filters like:
    "publication_year >= 2023 AND is_oa = true"

    Args:
        filters: Dict with publication_year, is_oa, has_abstract,
                 has_content_pdf, has_content_grobid_xml keys

    Returns:
        SQL-style filter string or None
    """
    if not filters:
        return None

    clauses = []

    if "publication_year" in filters:
        year_filter = str(filters["publication_year"])
        if year_filter.startswith(">="):
            clauses.append(f"publication_year >= {int(year_filter[2:])}")
        elif year_filter.startswith("<="):
            clauses.append(f"publication_year <= {int(year_filter[2:])}")
        elif year_filter.startswith(">"):
            clauses.append(f"publication_year > {int(year_filter[1:])}")
        elif year_filter.startswith("<"):
            clauses.append(f"publication_year < {int(year_filter[1:])}")
        elif "-" in year_filter:
            start, end = year_filter.split("-")
            clauses.append(f"publication_year >= {int(start)}")
            clauses.append(f"publication_year <= {int(end)}")
        else:
            clauses.append(f"publication_year = {int(year_filter)}")

    # Boolean filters: use SQL IS TRUE/IS FALSE syntax
    if "is_oa" in filters:
        if str(filters["is_oa"]).lower() == "true":
            clauses.append("is_oa IS TRUE")
        else:
            clauses.append("is_oa IS FALSE")

    if "has_abstract" in filters:
        if str(filters["has_abstract"]).lower() == "true":
            clauses.append("has_abstract IS TRUE")
        else:
            clauses.append("has_abstract IS FALSE")

    if "has_content_pdf" in filters:
        if str(filters["has_content_pdf"]).lower() == "true":
            clauses.append("has_content_pdf IS TRUE")
        else:
            clauses.append("has_content_pdf IS FALSE")

    if "has_content_grobid_xml" in filters:
        if str(filters["has_content_grobid_xml"]).lower() == "true":
            clauses.append("has_content_grobid_xml IS TRUE")
        else:
            clauses.append("has_content_grobid_xml IS FALSE")

    return " AND ".join(clauses) if clauses else None


def search_vectors(
    query_text: str,
    num_results: int = 10,
    filters: dict = None
) -> tuple:
    """
    Search Databricks Vector Search for similar works.

    Uses self-managed embeddings: we embed the query using ai_query,
    then search with the query vector.

    Args:
        query_text: Query text (we embed it using databricks-gte-large-en)
        num_results: Number of results to return
        filters: Optional metadata filters (publication_year, type, is_oa, has_abstract)

    Returns:
        Tuple of (results list, timing dict)
        - results: List of dicts with work_id and score
        - timing: Dict with embed_ms and search_ms
    """
    timing = {}

    # Step 1: Embed the query text
    t0 = time.time()
    query_vector = embed_query(query_text)
    timing["embed_ms"] = round((time.time() - t0) * 1000)

    # Step 2: Search with the query vector
    t0 = time.time()
    vsc = get_vector_search_client()
    index = vsc.get_index(VECTOR_SEARCH_ENDPOINT, VECTOR_SEARCH_INDEX)

    # Build filter string for storage-optimized endpoint
    filter_str = build_filter_string(filters)

    # Perform similarity search with query vector
    results = index.similarity_search(
        query_vector=query_vector,
        num_results=num_results,
        columns=["work_id"],
        filters=filter_str
    )
    timing["search_ms"] = round((time.time() - t0) * 1000)

    # Parse results: work_id is first column, score is last column
    data_array = results.get('result', {}).get('data_array', [])
    return [{"work_id": row[0], "score": row[-1]} for row in data_array], timing


def hydrate_works(work_ids: list) -> dict:
    """
    Fetch full work objects from Elasticsearch.

    Args:
        work_ids: List of OpenAlex work IDs (integers or strings)

    Returns:
        Dict mapping work_id (integer) to work object
    """
    if not work_ids:
        return {}

    # Convert work_ids to OpenAlex URL format for ES query
    openalex_ids = [f"https://openalex.org/W{wid}" for wid in work_ids]

    es = connections.get_connection('walden')
    s = Search(index=WORKS_INDEX, using=es)

    # Search by ID
    s = s.query(Q("terms", id=openalex_ids))
    s = s.extra(size=len(work_ids))

    response = s.execute()

    # Build lookup dict mapping string work_id to Hit object
    # WorksSchema expects Hit objects with .meta attribute
    works = {}
    for hit in response.hits:
        # Extract ID from URL (e.g., "https://openalex.org/W4286979530" -> "4286979530")
        str_id = hit.id.split("/W")[-1]
        works[str_id] = hit

    return works


def parse_filter(filter_str: str) -> dict:
    """
    Parse filter string into dict.

    Supported formats:
    - publication_year:2023
    - publication_year:>2020
    - publication_year:2020-2023
    - is_oa:true
    - has_abstract:true
    - has_content.pdf:true
    - has_content.grobid_xml:true

    Returns dict of filter key-value pairs.
    """
    if not filter_str:
        return {}

    # Map API filter names to internal names (dots to underscores for column names)
    filter_name_map = {
        "publication_year": "publication_year",
        "is_oa": "is_oa",
        "has_abstract": "has_abstract",
        "has_content.pdf": "has_content_pdf",
        "has_content.grobid_xml": "has_content_grobid_xml",
    }

    filters = {}
    for part in filter_str.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key in filter_name_map:
            filters[filter_name_map[key]] = value

    return filters


def normalize_filter_dict(filters: dict) -> dict:
    """
    Normalize filter dict keys from API format to internal format.
    Maps dots to underscores (e.g., has_content.pdf -> has_content_pdf).
    """
    filter_name_map = {
        "publication_year": "publication_year",
        "is_oa": "is_oa",
        "has_abstract": "has_abstract",
        "has_content.pdf": "has_content_pdf",
        "has_content.grobid_xml": "has_content_grobid_xml",
    }
    return {filter_name_map.get(k, k): v for k, v in filters.items() if k in filter_name_map}


@blueprint.route("/find/works", methods=["GET", "POST"])
def find_works():
    """
    Semantic similarity search over OpenAlex works.

    GET /find/works?query=...&count=25&filter=publication_year:>2020

    POST /find/works
    {
        "query": "full text query...",
        "count": 25,
        "filter": {
            "publication_year": ">2020",
            "is_oa": true,
            "has_content.pdf": true
        }
    }

    Parameters:
        query: Search text (required, max 10,000 chars)
        count: Number of results (1-100, default 25)
        filter: Optional filters:
            - publication_year: e.g., "2023", ">2020", ">=2020", "2020-2023"
            - is_oa: true/false
            - has_abstract: true/false
            - has_content.pdf: true/false
            - has_content.grobid_xml: true/false

    Returns:
    {
        "meta": {
            "count": 25,
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
        count = data.get("count", DEFAULT_COUNT)
        filters = data.get("filter", {})
        if isinstance(filters, str):
            filters = parse_filter(filters)
        else:
            filters = normalize_filter_dict(filters)
    else:
        query = request.args.get("query", "").strip()
        count = request.args.get("count", DEFAULT_COUNT, type=int)
        filter_str = request.args.get("filter", "")
        filters = parse_filter(filter_str)

    # Validate query
    if not query:
        raise APIQueryParamsError("query parameter is required")

    if len(query) > 10000:
        raise APIQueryParamsError("query must be at most 10,000 characters")

    # Validate count
    try:
        count = int(count)
    except (ValueError, TypeError):
        raise APIQueryParamsError("count must be an integer")

    if count < 1:
        raise APIQueryParamsError("count must be at least 1")
    if count > MAX_COUNT:
        raise APIQueryParamsError(f"count must be at most {MAX_COUNT}")

    total_start = time.time()
    timing = {}

    # Step 1: Vector search (includes embedding)
    try:
        vector_results, vector_timing = search_vectors(
            query_text=query,
            num_results=count,
            filters=filters
        )
        timing.update(vector_timing)
    except Exception as e:
        raise APIQueryParamsError(f"Vector search failed: {str(e)}")

    # Step 2: Hydrate from Elasticsearch
    t0 = time.time()
    work_ids = [r["work_id"] for r in vector_results]
    try:
        works = hydrate_works(work_ids)
    except Exception as e:
        raise APIQueryParamsError(f"Hydration failed: {str(e)}")
    timing["hydrate_ms"] = round((time.time() - t0) * 1000)

    # Step 3: Build response
    t0 = time.time()
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
    timing["serialize_ms"] = round((time.time() - t0) * 1000)
    timing["total_ms"] = round((time.time() - total_start) * 1000)

    return jsonify({
        "meta": {
            "count": len(results),
            "query": query,
            "filters_applied": filters if filters else None,
            "timing": timing
        },
        "results": results
    })


def get_embeddings_count():
    """Get count of embeddings from the source table."""
    try:
        host = settings.DATABRICKS_HOST.replace("https://", "").replace("http://", "")
        with databricks_sql.connect(
            server_hostname=host,
            http_path=settings.DATABRICKS_HTTP_PATH,
            access_token=settings.DATABRICKS_TOKEN
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM openalex.vector_search.work_embeddings_v2")
                result = cursor.fetchone()
                return result[0] if result else None
    except Exception:
        return None


@blueprint.route("/find/works/health", methods=["GET"])
def find_works_health():
    """Health check endpoint."""
    checks = {
        "databricks": False,
        "elasticsearch": False
    }
    index_status = None

    # Check Databricks Vector Search and get index status
    try:
        vsc = get_vector_search_client()
        index = vsc.get_index(VECTOR_SEARCH_ENDPOINT, VECTOR_SEARCH_INDEX)
        checks["databricks"] = True

        # Get index sync status
        desc = index.describe()
        status = desc.get("status", {})
        index_status = {
            "ready": status.get("ready", False),
            "state": status.get("detailed_state", "UNKNOWN"),
            "indexed_row_count": status.get("indexed_row_count"),
            "embedding_model": EMBEDDING_MODEL,
            "total_works_with_abstracts": TOTAL_WORKS_WITH_ABSTRACTS
        }

        # Get sync progress - check both initial sync and triggered update paths
        sync_completion = None

        # Path 1: Initial pipeline sync (during first sync)
        prov_status = status.get("provisioning_status", {})
        initial_sync = prov_status.get("initial_pipeline_sync_progress", {})
        if initial_sync:
            sync_completion = initial_sync.get("sync_progress_completion")

        # Path 2: Triggered update (during manual syncs)
        triggered_status = status.get("triggered_update_status", {})
        triggered_progress = triggered_status.get("triggered_update_progress", {})
        if triggered_progress:
            sync_completion = triggered_progress.get("sync_progress_completion")

        if sync_completion is not None:
            index_status["sync_progress"] = round(sync_completion * 100, 1)

        # Get actual embeddings count from table
        embeddings_count = get_embeddings_count()
        if embeddings_count:
            index_status["embeddings_count"] = embeddings_count

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

    response = {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks
    }
    if index_status:
        response["index"] = index_status

    return jsonify(response), 200 if all_healthy else 503
