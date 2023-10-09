from collections import OrderedDict

from elasticsearch.exceptions import RequestError
from elasticsearch_dsl import Q, Search

import settings
from core.cursor import decode_cursor, get_next_cursor
from core.exceptions import APIPaginationError, APIQueryParamsError
from core.export import is_group_by_export
from core.filter import filter_records
from core.group_by import (
    filter_group_by,
    get_group_by_results,
    get_group_by_results_external_ids,
    group_by_best_open_version,
    group_by_continent,
    group_by_records,
    group_by_version,
    parse_group_by,
    search_group_by_results,
    validate_group_by,
)
from core.paginate import Paginate
from core.search import check_is_search_query, full_search_query
from core.sort import get_sort_fields
from core.utils import (
    clean_preference,
    get_all_groupby_values,
    get_field,
    map_filter_params,
    map_sort_params,
    set_number_param,
)
from core.validate import validate_export_format, validate_params


def shared_view(request, fields_dict, index_name, default_sort):
    """Primary function used to search, filter, and aggregate across all entities."""

    # params
    validate_params(request)
    cursor = request.args.get("cursor")
    validate_export_format(request.args.get("format"))
    filter_params = map_filter_params(request.args.get("filter"))
    group_by = request.args.get("group_by") or request.args.get("group-by")
    group_bys_param = request.args.get("group_bys") or request.args.get("group-bys")
    group_bys = group_bys_param.split(",") if group_bys_param else []
    page = set_number_param(request, "page", 1)
    sample = request.args.get("sample", type=int)
    seed = request.args.get("seed")

    # set per_page
    if is_group_by_export(request):
        per_page = 200
    elif not group_by:
        per_page = set_number_param(request, "per-page", 25)
    else:
        per_page = set_number_param(request, "per-page", 200)
    q = request.args.get("q")
    search = request.args.get("search")
    sort_params = map_sort_params(request.args.get("sort"))

    s = Search(index=index_name)
    if index_name.startswith("works"):
        s = s.source(excludes=["abstract", "fulltext", "authorships_full"])

    # pagination
    paginate = Paginate(group_by, page, per_page, sample)
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
        search_query = full_search_query(index_name, search)
        if sample:
            s = s.filter(search_query)
        else:
            s = s.query(search_query)
        s = s.params(preference=clean_preference(search))

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s, sample)

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
            s = s.params(preference=clean_preference(preference))

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
    elif sample:
        if seed:
            random_query = Q(
                "function_score",
                functions={"random_score": {"seed": seed, "field": "_seq_no"}},
            )
            s = s.params(preference=clean_preference(seed))
        else:
            random_query = Q("function_score", functions={"random_score": {}})
        s = s.query(random_query)
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
    if group_by:
        s = s.params(preference=clean_preference(group_by))
        group_by, known = parse_group_by(group_by)
        field = get_field(fields_dict, group_by)
        validate_group_by(field)
        if (
            field.param != "best_open_version"
            or field.param != "version"
            or "continent" not in field.param
        ):
            s = group_by_records(group_by, field, s, sort_params, known, per_page, q)
    elif group_bys:
        s = s.params(preference=clean_preference(group_by))
        for group_by_item in group_bys:
            group_by_item, known = parse_group_by(group_by_item)
            field = get_field(fields_dict, group_by_item)
            validate_group_by(field)
            if (
                field.param != "best_open_version"
                or field.param != "version"
                or "continent" not in field.param
            ):
                s = group_by_records(
                    group_by_item, field, s, sort_params, known, per_page, q
                )

    if group_by:
        if group_by and q and q != "''":
            s = filter_group_by(field, group_by, q, s)
        response = s.execute()

        # group by count
        if (
            group_by in settings.EXTERNAL_ID_FIELDS
            or group_by in settings.BOOLEAN_TEXT_FIELDS
            or "is_global_south" in group_by
        ):
            count = 2
        elif any(
            keyword in field.param
            for keyword in ["continent", "version", "best_open_version"]
        ):
            count = 3
        else:
            count = len(
                response.aggregations[f"groupby_{group_by.replace('.', '_')}"].buckets
            )
    elif group_bys:
        response = s.execute()
        count = 0
    else:
        try:
            response = s[paginate.start : paginate.end].execute()
        except RequestError as e:
            if "search_after has" in str(e) and "but sort has" in str(e):
                raise APIPaginationError("Cursor value is invalid.")
        count = s.count()

    if sample and sample < count:
        count = sample

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

    # handle group by results
    if group_by:
        if (
            group_by in settings.EXTERNAL_ID_FIELDS
            or group_by in settings.BOOLEAN_TEXT_FIELDS
            or "is_global_south" in group_by
        ):
            result["group_by"] = get_group_by_results_external_ids(response, group_by)
        elif "continent" in field.param:
            result["group_by"] = group_by_continent(
                field, index_name, search, filter_params, filter_records, fields_dict, q
            )
            result["meta"]["count"] = len(result["group_by"])
        elif field.param == "version":
            result["group_by"] = group_by_version(
                field, index_name, search, filter_params, filter_records, fields_dict, q
            )
            result["meta"]["count"] = len(result["group_by"])
        elif field.param == "best_open_version":
            result["group_by"] = group_by_best_open_version(
                field, index_name, search, filter_params, filter_records, fields_dict, q
            )
            result["meta"]["count"] = len(result["group_by"])
        else:
            result["group_by"] = get_group_by_results(group_by, response)
        # add in zero values
        ignore_values = set([item["key"] for item in result["group_by"]])
        if known:
            ignore_values.add("unknown")
            ignore_values.add("-111")
        possible_buckets = get_all_groupby_values(
            entity=index_name.split("-")[0], field=group_by
        )
        for bucket in possible_buckets:
            if bucket["key"] not in ignore_values and not bucket["key"].startswith(
                "http://metadata.un.org"
            ):
                result["group_by"].append(
                    {
                        "key": bucket["key"],
                        "key_display_name": bucket["key_display_name"],
                        "doc_count": 0,
                    }
                )
    elif group_bys:
        result["group_bys"] = []
        for group_by_item in group_bys:
            group_by_item, known = parse_group_by(group_by_item)
            if (
                group_by_item in settings.EXTERNAL_ID_FIELDS
                or group_by_item in settings.BOOLEAN_TEXT_FIELDS
                or "is_global_south" in group_by_item
            ):
                item_results = get_group_by_results_external_ids(
                    response, group_by_item
                )
            elif "continent" in group_by_item:
                item_results = group_by_continent(
                    field,
                    index_name,
                    search,
                    filter_params,
                    filter_records,
                    fields_dict,
                    q,
                )
            elif group_by_item == "version":
                item_results = group_by_version(
                    field,
                    index_name,
                    search,
                    filter_params,
                    filter_records,
                    fields_dict,
                    q,
                )
            elif group_by_item == "best_open_version":
                item_results = group_by_best_open_version(
                    field,
                    index_name,
                    search,
                    filter_params,
                    filter_records,
                    fields_dict,
                    q,
                )
            else:
                item_results = get_group_by_results(group_by_item, response)
            # add in zero values
            ignore_values = set([item["key"] for item in item_results])
            if known:
                ignore_values.add("unknown")
                ignore_values.add("-111")
            possible_buckets = get_all_groupby_values(
                entity=index_name.split("-")[0], field=group_by_item
            )
            for bucket in possible_buckets:
                if bucket["key"] not in ignore_values:
                    item_results.append(
                        {
                            "key": bucket["key"],
                            "key_display_name": bucket["key_display_name"],
                            "doc_count": 0,
                        }
                    )
            result["group_bys"].append(
                {
                    "group_by_key": group_by_item,
                    "groups": item_results,
                }
            )
        result["group_by"] = []
    else:
        result["group_by"] = []
        result["results"] = response

    if "q" in request.args:
        result["meta"]["q"] = q

    # search group bys
    if group_by and q and q != "''":
        result["group_by"] = search_group_by_results(
            group_by, q, result["group_by"], per_page
        )
        result["meta"]["count"] = len(result["group_by"])
    elif group_bys and q and q != "''":
        for group_by_item in group_bys:
            group_by_item, known = parse_group_by(group_by_item)
            for group in result["group_bys"]:
                if group["group_by_key"] == group_by_item:
                    group["groups"] = search_group_by_results(
                        group_by_item, q, group["groups"], per_page
                    )
                    break
    if settings.DEBUG:
        print(s.to_dict())
    return result
