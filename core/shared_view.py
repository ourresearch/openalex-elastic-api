from collections import OrderedDict

from elasticsearch_dsl import Search

from core.cursor_pagination import decode_cursor, encode_cursor, get_cursor
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.group_by import get_group_by_results, group_by_records
from core.paginate import Paginate
from core.sort import sort_records
from core.utils import (get_field, map_filter_params, map_sort_params,
                        set_number_param)
from core.validate import validate_params


def shared_view(request, fields_dict, index_name, default_sort):
    validate_params(request)
    cursor = request.args.get("cursor")
    filter_params = map_filter_params(request.args.get("filter"))
    group_by = request.args.get("group_by") or request.args.get("group-by")
    page = set_number_param(request, "page", 1)
    per_page = (
        set_number_param(request, "per-page", 25)
        if not group_by
        else set_number_param(request, "per-page", 200)
    )
    sort_params = map_sort_params(request.args.get("sort"))

    paginate = Paginate(group_by, page, per_page)
    paginate.validate()

    s = Search(index=index_name)

    if group_by:
        s = s.extra(size=0)
    else:
        s = s.extra(size=per_page)

    if cursor and cursor != "*":
        decoded_cursor = decode_cursor(cursor)
        s = s.extra(search_after=decoded_cursor)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    is_search_query = False

    if filter_params:
        for filter in filter_params:
            if (
                "display_name.search" in filter.keys()
                and filter["display_name.search"] != ""
                or "title.search" in filter.keys()
                and filter["title.search"] != ""
            ):
                is_search_query = True
                break

    # sort
    # do not allow sorting by relevance score without search query
    if (
        not is_search_query
        and sort_params
        and "relevance_score" in sort_params
        and sort_params["relevance_score"] == "desc"
    ):
        del sort_params["relevance_score"]

    if sort_params:
        s = sort_records(fields_dict, group_by, sort_params, s)
    elif is_search_query and not sort_params and index_name.startswith("works"):
        s = s.sort("_score", "publication_date")
    elif is_search_query and not sort_params:
        s = s.sort("_score", "-works_count")
    elif not group_by:
        s = s.sort(*default_sort)

    # group by
    if group_by:
        field = get_field(fields_dict, group_by)
        if (
            type(field).__name__ == "DateField"
            or type(field).__name__ == "RangeField"
            and field.param != "publication_year"
            and field.param != "level"
        ):
            raise APIQueryParamsError("Cannot group by date or number fields.")
        elif field.param == "referenced_works":
            raise APIQueryParamsError(
                "Group by referenced_works is not supported at this time."
            )
        s = group_by_records(field, s, sort_params)

    if not group_by:
        response = s[paginate.start : paginate.end].execute()
        count = s.count()
    else:
        response = s.execute()
        count = len(response.aggregations.groupby.buckets)

    result = OrderedDict()
    result["meta"] = {
        "count": count,
        "db_response_time_ms": response.took,
        "page": page if not cursor else None,
        "per_page": 200 if group_by else per_page,
    }
    result["results"] = []

    if cursor:
        elastic_cursor = get_cursor(response)
        next_cursor = encode_cursor(elastic_cursor) if elastic_cursor else None
        result["meta"]["next_cursor"] = next_cursor

    if group_by:
        result["group_by"] = get_group_by_results(group_by, response)
    else:
        result["group_by"] = []
        result["results"] = response
    # print(s.to_dict())
    return result
