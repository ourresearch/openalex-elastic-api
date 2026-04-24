from core.paginate import get_per_page
from core.utils import map_filter_params, map_sort_params, set_number_param
from core.validate import validate_export_format, validate_params


def parse_params(request):
    """Extract and validate parameters from the request."""
    validate_params(request)

    # Determine search type, scope, and query from search.* dot notation params
    search_type, search_scope, search_query = _extract_search_params(request)
    searches = _extract_all_search_params(request)

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
        "search_scope": search_scope,
        "searches": searches,
        "sort": map_sort_params(request.args.get("sort")),
    }
    if params["group_bys"]:
        params["group_bys"] = params["group_bys"].split(",")
    return params


def _extract_all_search_params(request):
    """Extract all search params from the request as a list of dicts.

    Each dict has keys: search (query string), search_type, search_scope.
    Returns an empty list if no search params are present.
    """
    # Map param names to (search_type, search_scope)
    param_map = {
        "search": ("default", None),
        "search.exact": ("exact", None),
        "search.semantic": ("semantic", None),
        "search.title": ("default", "title"),
        "search.title.exact": ("exact", "title"),
        "search.title_and_abstract": ("default", "title_and_abstract"),
        "search.title_and_abstract.exact": ("exact", "title_and_abstract"),
    }

    results = []
    for param_name, (search_type, search_scope) in param_map.items():
        value = request.args.get(param_name)
        if value:
            results.append({
                "search": value,
                "search_type": search_type,
                "search_scope": search_scope,
            })
    return results


def _extract_search_params(request):
    """
    Extract search type, scope, and query from request args.

    Returns (search_type, search_scope, search_query):
        search=query                         -> ("default", None, "query")
        search.semantic=query                -> ("semantic", None, "query")
        search.exact=query                   -> ("exact", None, "query")
        search.title=query                   -> ("default", "title", "query")
        search.title.exact=query             -> ("exact", "title", "query")
        search.title_and_abstract=query      -> ("default", "title_and_abstract", "query")
        search.title_and_abstract.exact=query-> ("exact", "title_and_abstract", "query")
        (no search param)                    -> (None, None, None)
    """
    # Check for field-scoped params first
    for scope in ("title_and_abstract", "title"):
        exact_key = f"search.{scope}.exact"
        default_key = f"search.{scope}"
        if request.args.get(exact_key):
            return "exact", scope, request.args.get(exact_key)
        if request.args.get(default_key):
            return "default", scope, request.args.get(default_key)

    # Non-scoped dot notation params
    if request.args.get("search.semantic"):
        return "semantic", None, request.args.get("search.semantic")
    if request.args.get("search.exact"):
        return "exact", None, request.args.get("search.exact")

    # Fall back to bare search param
    if request.args.get("search"):
        return "default", None, request.args.get("search")

    return None, None, None
