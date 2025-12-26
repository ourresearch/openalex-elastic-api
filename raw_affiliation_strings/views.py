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


def format_institution_id(id_str):
    """Convert institution ID to fully-qualified format."""
    # IDs already have I prefix in v2 index
    if id_str.startswith("I"):
        return f"https://openalex.org/{id_str}"
    return f"https://openalex.org/I{id_str}"


def parse_works_count(value):
    """
    Parse works_count filter value.
    Formats:
    - "42" -> exact match
    - "42-" -> >= 42
    - "-42" -> <= 42
    - "42-100" -> between 42 and 100 inclusive
    Returns dict with 'gte' and/or 'lte' keys, or 'exact' key.
    """
    if not value:
        return None
    value = str(value).strip()
    
    # Check for range format "X-Y"
    if "-" in value:
        # Handle "-42" (less than or equal)
        if value.startswith("-"):
            try:
                return {"lte": int(value[1:])}
            except ValueError:
                return None
        
        # Handle "42-" (greater than or equal)
        if value.endswith("-"):
            try:
                return {"gte": int(value[:-1])}
            except ValueError:
                return None
        
        # Handle "42-100" (between)
        parts = value.split("-", 1)
        if len(parts) == 2:
            try:
                return {"gte": int(parts[0]), "lte": int(parts[1])}
            except ValueError:
                return None
    
    # Exact match
    try:
        return {"exact": int(value)}
    except ValueError:
        return None


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
    - matched-institutions: comma-separated institution IDs to filter by (must be in institution_ids_final)
    - unmatched-institutions: comma-separated institution IDs to exclude (must NOT be in institution_ids_final)
    - works_count: filter by works count (e.g., 42, 42-, -42, 42-100)
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
    works_count_param = request.args.get("works_count", "").strip()
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
    
    # Parse works_count filter
    works_count_filter = None
    if works_count_param:
        works_count_filter = parse_works_count(works_count_param)
        if works_count_filter is None:
            raise APIQueryParamsError(
                f"Invalid works_count format: {works_count_param}. "
                "Use: 42 (exact), 42- (>=), -42 (<=), or 42-100 (range)."
            )
    
    # Parse institution IDs
    matched_institution_ids = []
    if matched_institutions_param:
        for id_str in matched_institutions_param.split(","):
            parsed_id = parse_institution_id(id_str.strip())
            if parsed_id is None:
                raise APIQueryParamsError(f"Invalid institution ID: {id_str}")
            # Format as "I{id}" for matching against institution_ids_final
            matched_institution_ids.append(f"I{parsed_id}")
    
    unmatched_institution_ids = []
    if unmatched_institutions_param:
        for id_str in unmatched_institutions_param.split(","):
            parsed_id = parse_institution_id(id_str.strip())
            if parsed_id is None:
                raise APIQueryParamsError(f"Invalid institution ID: {id_str}")
            # Format as "I{id}" for matching against institution_ids_final
            unmatched_institution_ids.append(f"I{parsed_id}")
    
    # Build Elasticsearch query using elasticsearch-dsl
    # Use 'walden' connection where this index lives
    es = connections.get_connection('walden')
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
    
    # Filter for matched institutions (must be in institution_ids_final)
    if matched_institution_ids:
        must_queries.append(Q("terms", institution_ids_final=matched_institution_ids))
    
    # Filter for unmatched institutions (must NOT be in institution_ids_final)
    if unmatched_institution_ids:
        must_queries.append(Q(
            "bool",
            must_not=[Q("terms", institution_ids_final=unmatched_institution_ids)]
        ))
    
    # Filter for works_count
    if works_count_filter:
        if "exact" in works_count_filter:
            must_queries.append(Q("term", works_count=works_count_filter["exact"]))
        else:
            range_params = {}
            if "gte" in works_count_filter:
                range_params["gte"] = works_count_filter["gte"]
            if "lte" in works_count_filter:
                range_params["lte"] = works_count_filter["lte"]
            must_queries.append(Q("range", works_count=range_params))
    
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
    
    # Sort by works_count descending (highest first), with _doc as tiebreaker for cursor pagination
    if not sample:
        s = s.sort("-works_count", "_doc")
    
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
        # IDs in v2 already have "I" prefix, filter out "-1" (no match)
        institution_ids_final = [
            format_institution_id(id_str)
            for id_str in source.get("institution_ids_final", [])
            if id_str and id_str != "-1"
        ]
        institution_ids_override = [
            format_institution_id(id_str)
            for id_str in source.get("institution_ids_override", [])
            if id_str and id_str != "-1"
        ]
        
        results.append({
            "raw_affiliation_string": source.get("raw_affiliation_string", ""),
            "works_count": source.get("works_count", 0),
            "institution_ids_final": institution_ids_final,
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
