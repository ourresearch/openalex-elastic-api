"""Semantic search for /keywords via the external keyword-search endpoint (oxjob #1464).

`GET /keywords?search.semantic=<text>` ranks keywords by meaning. The ranking comes from a
small external service (Modal), not from Elasticsearch kNN, so this path writes nothing to
any ES cluster and never touches the vector cluster:

1. POST {KEYWORD_SEARCH_URL}/search  {"query": <text>, "k": <1..200>}
   with `Authorization: Bearer {KEYWORD_SEARCH_TOKEN}`
   -> {"results": [{"id": "https://openalex.org/keywords/<kid>", "display_name": ...,
                    "score": <ranking score>, "similarity": <cosine>}, ...], ...}
2. Fetch those keyword docs from the keywords index by id (a READ-only `terms` query on
   `id.lower`, the same lookup the /keywords/<id> singleton uses), with the request's
   `filter=` applied as an ES filter. Ranked ids that fail the filter drop out.
3. Keep the endpoint's order, attach `relevance_score` = endpoint `score`, page in memory.
   The endpoint is always asked for k=200, so meta.count is the real ranked-list size.

Fallback: if the endpoint is unconfigured, errors, times out, or returns a malformed body,
`keyword_semantic_search` returns None and shared_view runs today's path, which treats
`search.semantic` on /keywords as a plain text search over the keyword names.
"""
import logging
import time
from collections import OrderedDict

import requests as http_requests
from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.utils import AttrDict

import settings
from core.exceptions import APIQueryParamsError
from core.filter import filter_records

logger = logging.getLogger(__name__)

# Same per_page cap as works semantic search (core/vector_index.MAX_SEMANTIC_RESULTS).
MAX_PER_PAGE = 50
# The endpoint's contract caps k at 200.
MAX_K = 200
KEYWORD_ID_PREFIX = "https://openalex.org/keywords/"


class KeywordSearchUnavailable(Exception):
    """The keyword-search endpoint could not give a usable answer; fall back."""


def is_keyword_semantic(params, index_name):
    return (
        index_name.lower().startswith("keywords")
        and params.get("search_type") == "semantic"
        and bool(params.get("search"))
        and params["search"] != '""'
        and bool(params["search"].strip())
    )


def keyword_search_configured():
    return bool(settings.KEYWORD_SEARCH_URL and settings.KEYWORD_SEARCH_TOKEN)


def validate_keyword_semantic_params(params):
    """Reject params the ranked-list path can't honor, the way works semantic does.

    group_by, cursor and `*.search` filters are rejected (one search method per request,
    as on works); per_page is capped at 50 and page * per_page at 200 (the ranked list's
    length). `sort` is ignored: results
    are always in ranking order (works semantic ignores sort the same way).
    """
    if params.get("group_by") or params.get("group_bys"):
        raise APIQueryParamsError(
            "group_by is not supported with semantic search. "
            "Use group_by with regular search instead."
        )
    if params.get("cursor"):
        raise APIQueryParamsError(
            "Cursor pagination is not supported with semantic search. "
            f"Use page/per_page pagination instead (max {MAX_PER_PAGE} results per page)."
        )
    for f in params.get("filters") or []:
        for key in f:
            if key.endswith(".search") or key.endswith(".search.exact"):
                raise APIQueryParamsError(
                    f"Cannot combine search.semantic with filter={key}. "
                    "Use only one search method per request."
                )
    per_page = params.get("per_page") or 25
    if per_page > MAX_PER_PAGE:
        raise APIQueryParamsError(
            f"per_page cannot exceed {MAX_PER_PAGE} for semantic search. "
            f"Received per_page={per_page}."
        )
    page = params.get("page") or 1
    if page * per_page > MAX_K:
        raise APIQueryParamsError(
            f"Semantic search on keywords returns at most {MAX_K} results: "
            f"page * per_page cannot exceed {MAX_K}. Received page={page}, per_page={per_page}."
        )


def fetch_ranked_keyword_ids(query, k):
    """Call the keyword-search endpoint; return [(keyword_id, score), ...] in ranked order.

    Raises KeywordSearchUnavailable on any transport, HTTP, or shape problem.
    """
    url = settings.KEYWORD_SEARCH_URL.rstrip("/") + "/search"
    headers = {"Authorization": f"Bearer {settings.KEYWORD_SEARCH_TOKEN}"}
    try:
        response = http_requests.post(
            url,
            headers=headers,
            json={"query": query, "k": k},
            timeout=settings.KEYWORD_SEARCH_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()["results"]
        ranked = []
        seen = set()
        for r in results:
            kid = str(r["id"]).lower()
            if not kid.startswith(KEYWORD_ID_PREFIX) or kid in seen:
                continue
            seen.add(kid)
            ranked.append((kid, float(r["score"])))
        return ranked
    except Exception as e:  # requests errors, bad JSON, missing keys, bad types
        raise KeywordSearchUnavailable(f"{type(e).__name__}: {e}") from e


def fetch_keyword_docs(ranked, params, fields_dict, index_name, connection):
    """Read the ranked keyword docs from ES (filters applied), in the endpoint's order."""
    if not ranked:
        return []
    ids = [kid for kid, _ in ranked]
    s = Search(index=index_name, using=connection)
    s = s.filter(Q("terms", id__lower=ids))
    if params.get("filters"):
        s = filter_records(fields_dict, params["filters"], s)
    s = s.extra(size=len(ids))
    response = s.execute()

    by_id = {}
    for hit in response:
        doc = hit.to_dict()
        by_id[str(doc.get("id", "")).lower()] = (hit.meta.id, doc)

    hits = []
    for kid, score in ranked:
        if kid not in by_id:
            continue  # filtered out, or not in the index
        es_id, doc = by_id[kid]
        obj = AttrDict(doc)
        obj.meta = AttrDict({"score": score, "id": es_id})
        hits.append(obj)
    return hits


def keyword_semantic_search(params, fields_dict, index_name, connection):
    """Serve /keywords?search.semantic=... from the keyword-search endpoint.

    Returns a shared_view-shaped result dict, or None to tell the caller to fall back to
    the plain text search. Param errors (group_by, cursor, per_page > 50) raise
    APIQueryParamsError before the endpoint is called.
    """
    validate_keyword_semantic_params(params)

    page = params.get("page") or 1
    per_page = params.get("per_page") or 25
    # Always ask for the full ranked list and page in memory, so meta.count is the
    # real number of ranked results (<= MAX_K), not capped by this page.
    k = MAX_K
    query = params["search"].strip()

    t0 = time.time()
    try:
        ranked = fetch_ranked_keyword_ids(query, k)
    except KeywordSearchUnavailable as e:
        logger.warning("KEYWORD_SEARCH fallback to text search: %s", e)
        print(f"KEYWORD_SEARCH_ERR fallback to text search: {e}", flush=True)
        return None

    hits = fetch_keyword_docs(ranked, params, fields_dict, index_name, connection)
    db_response_time_ms = int((time.time() - t0) * 1000)

    start = (page - 1) * per_page
    result = OrderedDict()
    result["meta"] = {
        "count": len(hits),
        "db_response_time_ms": db_response_time_ms,
        "page": page,
        "per_page": per_page,
        "groups_count": None,
    }
    result["group_by"] = []
    result["results"] = hits[start:start + per_page]
    return result
