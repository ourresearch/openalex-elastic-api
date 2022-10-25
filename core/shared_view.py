from collections import OrderedDict

from elasticsearch.exceptions import RequestError
from elasticsearch_dsl import Search

import settings
from core.cursor import decode_cursor, get_next_cursor
from core.exceptions import (APIPaginationError, APIQueryParamsError,
                             APISearchError)
from core.filter import filter_records
from core.group_by import (filter_group_by, get_group_by_results,
                           get_group_by_results_external_ids,
                           get_group_by_results_transform,
                           group_by_global_region, group_by_records,
                           group_by_records_transform, is_transform,
                           search_group_by_results)
from core.paginate import Paginate
from core.search import check_is_search_query, full_search
from core.sort import get_sort_fields
from core.utils import (get_field, map_filter_params, map_sort_params,
                        set_number_param)
from core.validate import validate_export_format, validate_params


def shared_view(request, fields_dict, index_name, default_sort):
    """Primary function used to search, filter, and aggregate across all five entities."""

    # params
    validate_params(request)
    cursor = request.args.get("cursor")
    validate_export_format(request.args.get("format"))
    filter_params = map_filter_params(request.args.get("filter"))
    group_by = request.args.get("group_by") or request.args.get("group-by")
    page = set_number_param(request, "page", 1)
    per_page = (
        set_number_param(request, "per-page", 25)
        if not group_by
        else set_number_param(request, "per-page", 200)
    )
    q = request.args.get("q")
    search = request.args.get("search")
    sort_params = map_sort_params(request.args.get("sort"))

    s = Search(index=index_name)
    if index_name.startswith("works"):
        s = s.source(excludes=["abstract", "fulltext"])

    # pagination
    paginate = Paginate(group_by, page, per_page)
    paginate.validate()

    if group_by:
        s = s.extra(size=0)
    else:
        s = s.extra(size=per_page)

    if cursor and page != 1:
        raise APIPaginationError("Cannot use page parameter with cursor.")

    if cursor and cursor != "*":
        decoded_cursor = decode_cursor(cursor)
        s = s.extra(search_after=decoded_cursor)

    # search
    if search and search != '""':
        s = full_search(index_name, s, search)
        s = s.params(preference=search)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

        # set preference key if search param present. ensures
        preference = None
        for filter_param in filter_params:
            for key in filter_param:
                if key in [
                    "abstract.search",
                    "display_name.search",
                    "title.search",
                    "raw_affiliation_string.search",
                ]:
                    preference = filter_param[key]
        if preference:
            s = s.params(preference=preference)

    # sort
    is_search_query = check_is_search_query(filter_params, search)
    # do not allow sorting by relevance score without search query
    if not is_search_query and sort_params and "relevance_score" in sort_params:
        raise APIQueryParamsError(
            "Must include a search query (such as ?search=example or /filter=display_name.search:example) in order to sort by relevance_score."
        )

    if sort_params and cursor:
        # add default sort if paginating with a cursor
        sort_fields = get_sort_fields(fields_dict, group_by, sort_params)
        sort_fields_with_default = sort_fields + default_sort
        s = s.sort(*sort_fields_with_default)
    elif sort_params:
        sort_fields = get_sort_fields(fields_dict, group_by, sort_params)
        s = s.sort(*sort_fields)
    elif is_search_query and not sort_params and index_name.startswith("works"):
        s = s.sort("_score", "publication_date", "id")
    elif is_search_query and not sort_params:
        s = s.sort("_score", "-works_count", "id")
    elif not group_by:
        s = s.sort(*default_sort)

    # group by
    transform = False
    if group_by:
        s = s.params(preference=group_by)
        # handle known filter
        known = False
        if ":" in group_by:
            group_by_split = group_by.split(":")
            if len(group_by_split) == 2 and group_by_split[1].lower() == "known":
                group_by = group_by_split[0]
                known = True
            elif len(group_by_split) == 2 and group_by_split[1].lower() != "known":
                raise APIQueryParamsError(
                    "The only valid filter for a group_by param is 'known', which hides the unknown group from results."
                )
        field = get_field(fields_dict, group_by)
        transform = is_transform(field, index_name, filter_params)
        if (
            type(field).__name__ == "DateField"
            or (
                type(field).__name__ == "RangeField"
                and field.param != "cited_by_count"
                and field.param != "level"
                and field.param != "publication_year"
                and field.param != "works_count"
            )
            or type(field).__name__ == "SearchField"
        ):
            raise APIQueryParamsError("Cannot group by date, number, or search fields.")
        elif field.param == "referenced_works":
            raise APIQueryParamsError(
                "Group by referenced_works is not supported at this time."
            )
        elif field.param in settings.DO_NOT_GROUP_BY:
            raise APIQueryParamsError(f"Cannot group by {field.param}.")
        if transform:
            s = group_by_records_transform(field, index_name, sort_params)
        elif field.param in settings.GLOBAL_REGION_FIELDS:
            return group_by_global_region(
                field,
                index_name,
                search,
                full_search,
                filter_params,
                filter_records,
                fields_dict,
            )
        else:
            s = group_by_records(field, s, sort_params, known, per_page, q)

    if not group_by:
        try:
            response = s[paginate.start : paginate.end].execute()
        except RequestError as e:
            if "search_after has" in str(e) and "but sort has" in str(e):
                raise APIPaginationError("Cursor value is invalid.")
            else:
                raise APISearchError("Something went wrong.")
        count = s.count()
    else:
        if group_by and q and q != "''":
            s = filter_group_by(field, group_by, q, s)
        response = s.execute()
        if (
            group_by in settings.EXTERNAL_ID_FIELDS
            or group_by in settings.BOOLEAN_TEXT_FIELDS
        ):
            count = 2
        elif transform:
            count = len(response)
        else:
            if (
                "nested_groupby" in response.aggregations
                and "inner" in response.aggregations.nested_groupby
            ):
                count = len(response.aggregations.nested_groupby.inner.groupby.buckets)
            elif "nested_groupby" in response.aggregations:
                count = len(response.aggregations.nested_groupby.groupby.buckets)
            else:
                count = len(response.aggregations.groupby.buckets)

    result = OrderedDict()
    result["meta"] = {
        "count": count,
        "db_response_time_ms": response.took,
        "page": page if not cursor else None,
        "per_page": per_page,
    }
    result["results"] = []

    if cursor:
        result["meta"]["next_cursor"] = get_next_cursor(response)

    if group_by:
        if (
            group_by in settings.EXTERNAL_ID_FIELDS
            or group_by in settings.BOOLEAN_TEXT_FIELDS
        ):
            result["group_by"] = get_group_by_results_external_ids(response)
        elif transform:
            result["group_by"] = get_group_by_results_transform(group_by, response)
        else:
            result["group_by"] = get_group_by_results(group_by, response)
    else:
        result["group_by"] = []
        result["results"] = response

    if "q" in request.args:
        result["meta"]["q"] = q

    if group_by and q and q != "''":
        result["group_by"] = search_group_by_results(
            group_by, q, result["group_by"], per_page
        )
        result["meta"]["count"] = len(result["group_by"])
    if settings.DEBUG:
        print(s.to_dict())
    return result
