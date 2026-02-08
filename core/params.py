from core.paginate import get_per_page
from core.utils import map_filter_params, map_sort_params, set_number_param
from core.validate import validate_export_format, validate_params


def parse_params(request):
    """Extract and validate parameters from the request."""
    validate_params(request)

    # Determine search type and query from search.* dot notation params
    search_type, search_query = _extract_search_params(request)

    params = {
        "apc_sum": request.args.get("apc_sum"),
        "cited_by_count_sum": request.args.get("cited_by_count_sum"),
        "cursor": request.args.get("cursor"),
        "format": validate_export_format(request.args.get("format")),
        "filters": map_filter_params(request.args.get("filter")),
        "group_by": request.args.get("group_by") or request.args.get("group-by"),
        "group_bys": request.args.get("group_bys") or request.args.get("group-bys"),
        "page": set_number_param(request, "page", 1),
        "per_page": get_per_page(request),
        "sample": request.args.get("sample", type=int),
        "seed": request.args.get("seed"),
        "q": request.args.get("q"),
        "search": search_query,
        "search_type": search_type,
        "sort": map_sort_params(request.args.get("sort")),
    }
    if params["group_bys"]:
        params["group_bys"] = params["group_bys"].split(",")
    return params


def _extract_search_params(request):
    """
    Extract search type and query from request args.

    Supports dot notation:
        search=query          -> ("default", "query")
        search.semantic=query -> ("semantic", "query")
        search.exact=query    -> ("exact", "query")
        (no search param)     -> (None, None)
    """
    # Check for dot notation params first
    if request.args.get("search.semantic"):
        return "semantic", request.args.get("search.semantic")
    if request.args.get("search.exact"):
        return "exact", request.args.get("search.exact")

    # Fall back to bare search param
    if request.args.get("search"):
        return "default", request.args.get("search")

    return None, None
