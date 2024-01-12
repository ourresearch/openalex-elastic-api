from collections import OrderedDict

from elasticsearch.exceptions import RequestError
from elasticsearch_dsl import Search

import settings
from core.cursor import get_next_cursor, handle_cursor
from core.exceptions import APIPaginationError, APIQueryParamsError
from core.filter import filter_records
from core.group_by.results import get_group_by_results, calculate_group_by_count
from core.group_by.filter import filter_group_by
from core.group_by.utils import parse_group_by
from core.group_by.search import search_group_by_strings_with_q
from core.group_by.buckets import create_group_by_buckets
from core.paginate import get_pagination
from core.params import parse_params
from core.preference import clean_preference, set_preference_for_filter_search
from core.search import check_is_search_query, full_search_query
from core.sort import get_sort_fields, sort_with_cursor, sort_with_sample
from core.utils import get_field


def shared_view(request, fields_dict, index_name, default_sort):
    """Primary function used to search, filter, and aggregate across all entities."""
    params = parse_params(request)
    s = construct_query(params, fields_dict, index_name, default_sort)
    response = execute_search(s, params)
    result = format_response(response, params, index_name, fields_dict, s)
    if settings.DEBUG:
        print(s.to_dict())
    return result


def construct_query(params, fields_dict, index_name, default_sort):
    s = Search(index=index_name)

    s = set_source(index_name, s)

    s = set_size(params, s)

    s = set_cursor_pagination(params, s)

    s = add_search_query(params, index_name, s)

    s = apply_filters(params, fields_dict, s)

    s = apply_sorting(params, fields_dict, default_sort, index_name, s)

    s = apply_grouping(params, fields_dict, s)

    s = filter_group_with_q(params, fields_dict, s)

    return s


def set_source(index_name, s):
    if index_name.startswith("works"):
        s = s.source(
            excludes=["abstract", "embeddings", "fulltext", "authorships_full"]
        )
    return s


def set_size(params, s):
    if params["group_by"]:
        s = s.extra(size=0)
    else:
        s = s.extra(size=params["per_page"])
    return s


def set_cursor_pagination(params, s):
    if not params["group_by"]:
        s = handle_cursor(params["cursor"], params["page"], s)
    return s


def add_search_query(params, index_name, s):
    if params["search"] and params["search"] != '""':
        search_query = full_search_query(index_name, params["search"])
        if params["sample"]:
            s = s.filter(search_query)
        else:
            s = s.query(search_query)
        s = s.params(preference=clean_preference(params["search"]))
    return s


def apply_filters(params, fields_dict, s):
    if params["filters"]:
        s = filter_records(fields_dict, params["filters"], s, params["sample"])
        s = set_preference_for_filter_search(params["filters"], s)
    return s


def apply_sorting(params, fields_dict, default_sort, index_name, s):
    is_search_query = check_is_search_query(params["filters"], params["search"])

    # do not allow sorting by relevance score without search query
    if not is_search_query and params["sort"] and "relevance_score" in params["sort"]:
        raise APIQueryParamsError(
            "Must include a search query (such as ?search=example or /filter=display_name.search:example) in order to sort by relevance_score."
        )

    if params["sort"] and params["cursor"]:
        s = sort_with_cursor(
            default_sort, fields_dict, params["group_by"], s, params["sort"]
        )
    elif params["sample"]:
        s = sort_with_sample(s, params["seed"])
    elif params["sort"]:
        sort_fields = get_sort_fields(fields_dict, params["group_by"], params["sort"])
        s = s.sort(*sort_fields)
    elif is_search_query and not params["sort"] and index_name.startswith("works"):
        s = s.sort("_score", "publication_date", "id")
    elif is_search_query and not params["sort"]:
        s = s.sort("_score", "-works_count", "id")
    elif not params["group_by"]:
        s = s.sort(*default_sort)
    return s


def apply_grouping(params, fields_dict, s):
    if params["group_by"]:
        group_by, include_unknown = parse_group_by(params["group_by"])
        s = create_group_by_buckets(fields_dict, group_by, include_unknown, s, params)
    elif params["group_bys"]:
        for group_by_item in params["group_bys"]:
            group_by, include_unknown = parse_group_by(group_by_item)
            s = create_group_by_buckets(
                fields_dict, group_by, include_unknown, s, params
            )
    return s


def filter_group_with_q(params, fields_dict, s):
    if params["group_by"] and params["q"] and params["q"] != "''":
        group_by, _ = parse_group_by(params["group_by"])
        field = get_field(fields_dict, group_by)
        s = filter_group_by(field, group_by, params["q"], s)
    return s


def execute_search(s, params):
    paginate = get_pagination(params)
    if params["group_by"]:
        response = s.execute()
    else:
        try:
            response = s[paginate.start : paginate.end].execute()
        except RequestError as e:
            if "search_after has" in str(e) and "sort has" in str(e):
                raise APIPaginationError("Cursor value is invalid.")
            raise e
    return response


def format_response(response, params, index_name, fields_dict, s):
    result = OrderedDict()

    result["meta"] = format_meta(response, params, s)

    if params["group_by"]:
        result["group_by"] = format_group_by(response, params, index_name, fields_dict)
    elif params["group_bys"]:
        result["group_bys"] = format_group_bys(
            response, params, index_name, fields_dict
        )
        result["group_by"] = []
    else:
        result["group_by"] = []
        result["results"] = response

    if params["q"] and params["q"] != "''":
        result = search_group_by_strings_with_q(params, result)

    return result


def format_meta(response, params, s):
    meta = {
        "count": calculate_sample_or_default_count(params, s),
        "db_response_time_ms": response.took,
        "page": params["page"] if not params["cursor"] else None,
        "per_page": params["per_page"],
        "groups_count": calculate_group_by_count(params, response)
        if params["group_by"]
        else None,
    }

    if params.get("cursor"):
        meta["next_cursor"] = get_next_cursor(params, response)

    return meta


def format_group_by(response, params, index_name, fields_dict):
    group_by, include_unknown = parse_group_by(params["group_by"])
    group_by_data = get_group_by_results(
        group_by, include_unknown, params, index_name, fields_dict, response
    )
    return group_by_data


def format_group_bys(response, params, index_name, fields_dict):
    group_bys_data = []

    for group_by_item in params["group_bys"]:
        group_by_item, include_unknown = parse_group_by(group_by_item)
        item_results = get_group_by_results(
            group_by_item, include_unknown, params, index_name, fields_dict, response
        )
        group_bys_data.append({"group_by_key": group_by_item, "groups": item_results})

    return group_bys_data


def calculate_sample_or_default_count(params, s):
    if params["sample"] and params["sample"] < s.count():
        return params["sample"]
    return s.count()
