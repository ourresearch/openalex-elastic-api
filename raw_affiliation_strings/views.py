import base64
import json

from elasticsearch_dsl import Search, Q
from flask import Blueprint, jsonify, request

import settings
from core.exceptions import APIQueryParamsError

blueprint = Blueprint("raw_affiliation_strings", __name__)

PER_PAGE = 100
MAX_OFFSET_PAGE = 100  # 100 pages * 100 per page = 10,000 max with offset paging


def parse_institution_id(id_str):
    """
    Parse an institution ID from various formats to integer.
    Accepts: I123, i123, https://openalex.org/I123, 123
    Returns integer or None if invalid.
    """
    if not id_str:
        return None
    id_str = str(id_str).strip()
    # Remove URL prefix if present
    if id_str.startswith("https://openalex.org/"):
        id_str = id_str[len("https://openalex.org/"):]
    # Remove I/i prefix if present
    if id_str.upper().startswith("I"):
        id_str = id_str[1:]
    try:
        return int(id_str)
    except ValueError:
        return None


def format_institution_id(id_int):
    """Convert integer institution ID to fully-qualified format."""
    return f"https://openalex.org/I{id_int}"


def encode_cursor(cursor_value):
    """Encode cursor value to base64."""
    cursor_json = json.dumps(cursor_value).encode()
    return base64.b64encode(cursor_json).decode()


def decode_cursor(encoded_cursor):
    """Decode base64 cursor to value."""
    if not encoded_cursor or encoded_cursor == "*":
        return None
    if encoded_cursor.lower() in ("null", "none"):
        return None
    try:
        decoded = base64.b64decode(encoded_cursor)
        return json.loads(decoded.decode("utf8"))
    except (json.JSONDecodeError, ValueError, Exception):
        return None


@blueprint.route("/raw-affiliation-strings")
def raw_affiliation_strings():
    """
    Search raw affiliation strings from the Elasticsearch index.
    
    Query params:
    - q: text query to match against raw_affiliation_string (supports phrase search, OR, exclusion, wildcards)
    - matched-institutions: comma-separated institution IDs to filter by (must be in institution_ids OR institution_ids_override)
    - unmatched-institutions: comma-separated institution IDs to exclude (must NOT be in institution_ids NOR institution_ids_override)
    - page: page number (1-indexed, max 100)
    - cursor: cursor for cursor-based pagination (use * to start)
    - sample: random sample size (max 10,000)
    - seed: seed for reproducible random sampling
    """
    from elasticsearch_dsl import connections
    
    # Parse query parameters
    q = request.args.get("q", "").strip()
    matched_institutions_param = request.args.get("matched-institutions", "").strip()
    unmatched_institutions_param = request.args.get("unmatched-institutions", "").strip()
    page_param = request.args.get("page", "1")
    cursor = request.args.get("cursor")
    sample_param = request.args.get("sample", "").strip()
    seed = request.args.get("seed", "").strip()
    
    # Validate and parse page
    try:
        page = int(page_param)
        if page < 1:
            raise APIQueryParamsError("page must be at least 1.")
    except ValueError:
        raise APIQueryParamsError("page must be an integer.")
    
    # Validate sample
    sample = None
    if sample_param:
        try:
            sample = int(sample_param)
            if sample < 1:
                raise APIQueryParamsError("sample must be at least 1.")
            if sample > 10000:
                raise APIQueryParamsError("sample must be at most 10,000.")
        except ValueError:
            raise APIQueryParamsError("sample must be an integer.")
    
    # Validate seed requires sample
    if seed and not sample:
        raise APIQueryParamsError("seed parameter requires sample parameter.")
    
    # Validate cursor and page conflict
    if cursor and cursor != "*" and page > 1:
        raise APIQueryParamsError("Cannot use page parameter with cursor.")
    
    # Validate page limit for offset-based pagination (without cursor)
    if not cursor and page > MAX_OFFSET_PAGE:
        raise APIQueryParamsError(
            f"Maximum page is {MAX_OFFSET_PAGE}. Use cursor pagination for deeper results."
        )
    
    # Parse institution IDs
    matched_institution_ids = []
    if matched_institutions_param:
        for id_str in matched_institutions_param.split(","):
            parsed_id = parse_institution_id(id_str.strip())
            if parsed_id is None:
                raise APIQueryParamsError(f"Invalid institution ID: {id_str}")
            matched_institution_ids.append(str(parsed_id))
    
    unmatched_institution_ids = []
    if unmatched_institutions_param:
        for id_str in unmatched_institutions_param.split(","):
            parsed_id = parse_institution_id(id_str.strip())
            if parsed_id is None:
                raise APIQueryParamsError(f"Invalid institution ID: {id_str}")
            unmatched_institution_ids.append(str(parsed_id))
    
    # Build Elasticsearch query using elasticsearch-dsl
    es = connections.get_connection('default')
    s = Search(index=settings.RAW_AFFILIATION_STRINGS_INDEX, using=es)
    
    # Build query parts
    must_queries = []
    
    # Text search on raw_affiliation_string
    if q:
        must_queries.append(Q(
            "simple_query_string",
            query=q,
            fields=["raw_affiliation_string"],
            default_operator="AND"
        ))
    
    # Filter for matched institutions (must be in either institution_ids OR institution_ids_override)
    if matched_institution_ids:
        must_queries.append(Q(
            "bool",
            should=[
                Q("terms", institution_ids=matched_institution_ids),
                Q("terms", institution_ids_override=matched_institution_ids)
            ],
            minimum_should_match=1
        ))
    
    # Filter for unmatched institutions (must NOT be in institution_ids NOR institution_ids_override)
    if unmatched_institution_ids:
        must_queries.append(Q(
            "bool",
            must_not=[
                Q("terms", institution_ids=unmatched_institution_ids),
                Q("terms", institution_ids_override=unmatched_institution_ids)
            ]
        ))
    
    # Combine query parts
    if must_queries:
        if len(must_queries) == 1:
            base_query = must_queries[0]
        else:
            base_query = Q("bool", must=must_queries)
    else:
        base_query = Q("match_all")
    
    # Handle sample (random scoring)
    if sample:
        if seed:
            s = s.query(Q(
                "function_score",
                query=base_query,
                functions=[{"random_score": {"seed": seed, "field": "_seq_no"}}]
            ))
        else:
            s = s.query(Q(
                "function_score",
                query=base_query,
                functions=[{"random_score": {}}]
            ))
    else:
        s = s.query(base_query)
    
    # Set size
    s = s.extra(size=PER_PAGE, track_total_hits=True)
    
    # Add sorting for cursor pagination (sort by _id for consistency)
    if not sample:
        s = s.sort({"_id": "asc"})
    
    # Handle cursor-based pagination
    if cursor and cursor != "*":
        decoded = decode_cursor(cursor)
        if decoded is None:
            raise APIQueryParamsError("Invalid cursor value.")
        s = s.extra(search_after=decoded)
    elif not cursor:
        # Offset-based pagination (works for both regular and sample queries)
        offset = (page - 1) * PER_PAGE
        s = s[offset:offset + PER_PAGE]
    
    # Limit size for sample - cap at sample size if it's less than remaining results
    if sample:
        offset = (page - 1) * PER_PAGE
        remaining = max(0, sample - offset)
        s = s.extra(size=min(remaining, PER_PAGE))
    
    # Execute search
    try:
        response = s.execute()
    except Exception as e:
        raise APIQueryParamsError(f"Search error: {str(e)}")
    
    # Extract results
    total = response.hits.total.value
    took = response.took
    
    # Format results
    results = []
    for hit in response.hits:
        source = hit.to_dict()
        
        # Convert institution IDs to fully-qualified format
        institution_ids = [
            format_institution_id(int(id_str)) 
            for id_str in source.get("institution_ids", [])
            if id_str
        ]
        institution_ids_override = [
            format_institution_id(int(id_str)) 
            for id_str in source.get("institution_ids_override", [])
            if id_str
        ]
        
        results.append({
            "raw_affiliation_string": source.get("raw_affiliation_string", ""),
            "institution_ids": institution_ids,
            "institution_ids_override": institution_ids_override,
            "countries": source.get("countries", [])
        })
    
    # Build meta
    meta = {
        "count": sample if sample and sample < total else total,
        "db_response_time_ms": took,
        "page": page if not cursor else None,
        "per_page": PER_PAGE,
        "q": q if q else None
    }
    
    # Add next_cursor for cursor-based pagination
    if cursor is not None:
        next_cursor = None
        if len(response.hits) == PER_PAGE:
            last_hit = response.hits[-1]
            if hasattr(last_hit.meta, 'sort') and last_hit.meta.sort:
                next_cursor = encode_cursor(list(last_hit.meta.sort))
        meta["next_cursor"] = next_cursor
    
    return jsonify({
        "meta": meta,
        "results": results
    })
