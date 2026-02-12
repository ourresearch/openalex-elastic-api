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
from core.group_by.buckets import add_meta_sums, create_group_by_buckets
from core.knn import KNNQueryWithFilter
from core.paginate import get_pagination
from core.params import parse_params
from core.preference import clean_preference, set_preference_for_filter_search
from core.search import check_is_search_query, full_search_query
from core.semantic_search import embed_query, VECTOR_FIELD
from core.sort import get_sort_fields, sort_with_cursor, sort_with_sample
from core.utils import get_data_version_connection, get_field


def shared_view(request, fields_dict, index_name, default_sort, connection=None, default_filters=None):
    """Primary function used to search, filter, and aggregate across all entities."""
    if connection is None:
        connection = get_data_version_connection(request)
    params = parse_params(request)

    # Merge default filters with user filters
    if default_filters:
        if params["filters"] is None:
            params["filters"] = default_filters
        else:
            # Add default filters that aren't already specified by user
            params["filters"] = default_filters + params["filters"]

    s = construct_query(params, fields_dict, index_name, default_sort, connection)
    response = execute_search(s, params)
    result = format_response(response, params, index_name, fields_dict, s, connection)
    if settings.DEBUG:
        print(s.to_dict())
    return result


def construct_query(params, fields_dict, index_name, default_sort, connection):
    s = Search(index=index_name, using=connection)

    s = set_source(index_name, s)

    s = set_size(params, s)

    s = set_cursor_pagination(params, s)

    is_semantic = (
        params.get("search_type") == "semantic"
        and params.get("search")
        and params["search"] != '""'
        and index_name.lower().startswith("works")
    )

    if is_semantic:
        s = add_semantic_search(params, fields_dict, s)
    else:
        s = add_search_query(params, index_name, s)
        s = apply_filters(params, fields_dict, s)

    s = apply_sorting(params, fields_dict, default_sort, index_name, s)

    s = apply_grouping(params, fields_dict, s)

    s = filter_group_with_q(params, fields_dict, s)

    s = add_meta_sums(params, index_name, s)

    s = add_highlighting(params, index_name, s)

    return s


def set_source(index_name, s):
    if index_name.startswith("works"):
        s = s.source(
            excludes=[
                "abstract",
                "embeddings",
                "fulltext",
                "authorships_full",
                "vector_embedding",
            ]
        )
    elif index_name.startswith("funder-search"):
        s = s.source(excludes=["html"])
    return s


def set_size(params, s):
    # Set track_total_hits to true to get accurate counts beyond 10k for all queries
    if params["group_by"]:
        s = s.extra(size=0, track_total_hits=True)
    else:
        s = s.extra(size=params["per_page"], track_total_hits=True)
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


# Filter keys that represent search operations — cannot be combined with semantic search
SEARCH_FILTER_KEYS = {
    "abstract.search", "default.search", "display_name.search",
    "fulltext.search", "keyword.search", "raw_affiliation_strings.search",
    "raw_author_name.search", "title.search", "title_and_abstract.search",
}


def add_semantic_search(params, fields_dict, s):
    """Build top-level kNN with pre-filtering for semantic search."""

    # Only one search mechanism at a time
    _reject_search_filters(params)

    query_vector = embed_query(params["search"])

    # Build filter dict from user params (reuses existing filter_records logic)
    filter_dict = _build_knn_filter(params, fields_dict)

    # Build kNN with pre-filter
    knn = KNNQueryWithFilter(
        field=VECTOR_FIELD,
        query_vector=query_vector,
        k=100,
        num_candidates=150,
        filter_query=filter_dict,
        similarity=0.5,
    )
    s = s.update_from_dict({"knn": knn.to_dict()})

    # Citation boost via rescore (only when returning hits, not group_by)
    if not (params.get("group_by") or params.get("group_bys")):
        s = _add_citation_rescore(s)

    s = s.params(preference=clean_preference(params["search"]))
    return s


def _reject_search_filters(params):
    """Raise error if semantic search is combined with search-type filters."""
    if not params.get("filters"):
        return
    for f in params["filters"]:
        for key in f:
            if key in SEARCH_FILTER_KEYS or key.endswith(".search"):
                raise APIQueryParamsError(
                    f"Cannot combine search.semantic with filter={key}. "
                    "Use only one search method per request."
                )


def _build_knn_filter(params, fields_dict):
    """Build ES filter dict from user params for kNN pre-filtering.

    Uses a temporary Search object + existing filter_records() to build
    the filter query, then extracts the dict representation.
    """
    if not params.get("filters"):
        return None

    temp_s = Search()
    temp_s = filter_records(fields_dict, params["filters"], temp_s, params.get("sample"))
    temp_dict = temp_s.to_dict()

    if "query" in temp_dict:
        return temp_dict["query"]
    return None


def _add_citation_rescore(s, window_size=100):
    """Add citation-count rescore to re-rank semantic results.

    Replicates the existing citation_boost_query(scaling_type="log") behavior:
    final_score = similarity * (1 + log(cited_by_count))
    """
    return s.extra(rescore={
        "window_size": window_size,
        "query": {
            "rescore_query": {
                "function_score": {
                    "query": {"match_all": {}},
                    "functions": [{
                        "script_score": {
                            "script": {
                                "source": (
                                    "if (doc['cited_by_count'].size() == 0 || "
                                    "doc['cited_by_count'].value <= 1) { return 0.5; } "
                                    "else { return 1 + Math.log(doc['cited_by_count'].value); }"
                                )
                            }
                        }
                    }],
                    "boost_mode": "replace"
                }
            },
            "query_weight": 1.0,
            "rescore_query_weight": 1.0,
            "score_mode": "multiply"
        }
    })


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

        # override cited_by_percentile_year into default sort
        if (
            sort_fields
            and sort_fields == ["-cited_by_percentile_year.min"]
            or sort_fields == ["-cited_by_percentile_year.max"]
        ):
            sort_fields = default_sort

        s = s.sort(*sort_fields)
    elif is_search_query and not params["sort"] and index_name.startswith("works"):
        s = s.sort("_score", "publication_date", "id")
    elif is_search_query and not params["sort"] and index_name.startswith("funder-search"):
        # Sort by relevance score for funder-search
        s = s.sort("_score", "doi")
    elif is_search_query and not params["sort"] and index_name.startswith("awards"):
        # Sort by relevance score for awards (no works_count field)
        s = s.sort("_score", "id")
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


def add_highlighting(params, index_name, s):
    if index_name.startswith("funder-search") and params["search"] and params["search"] != '""':
        s = s.highlight(
            'html',
            fragment_size=300,
            number_of_fragments=5,
            type='plain',
            pre_tags=['>>'],
            post_tags=['<<']
        )
    return s


def execute_search(s, params):
    paginate = get_pagination(params)

    # Add query timeout to prevent long-running queries
    s = s.params(timeout='10s')

    if params["group_by"]:
        return s.execute()
    else:
        try:
            return s[paginate.start:paginate.end].execute()
        except RequestError as e:
            if "search_after has" in str(e) and "sort has" in str(e):
                raise APIPaginationError("Cursor value is invalid.")
            raise e


def format_response(response, params, index_name, fields_dict, s, connection='default'):
    result = OrderedDict()

    result["meta"] = format_meta(response, params, s)

    if params["group_by"]:
        result["group_by"] = format_group_by(response, params, index_name, fields_dict, connection)
    elif params["group_bys"]:
        result["group_bys"] = format_group_bys(
            response, params, index_name, fields_dict, connection
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
        "count": calculate_sample_or_default_count(params, response),
        "db_response_time_ms": response.took,
        "page": params["page"] if not params["cursor"] else None,
        "per_page": params["per_page"],
        "groups_count": calculate_group_by_count(params, response)
        if params["group_by"]
        else None,
    }

    if params.get("cursor"):
        meta["next_cursor"] = get_next_cursor(params, response)

    if (
        hasattr(response, "aggregations")
        and "apc_list_sum_usd" in response.aggregations
    ):
        meta["apc_list_sum_usd"] = response.aggregations.apc_list_sum_usd.value

    if (
        hasattr(response, "aggregations")
        and "filtered_apc_paid_sum" in response.aggregations
    ):
        agg_result = response.aggregations.filtered_apc_paid_sum
        if "apc_paid_sum_usd" in agg_result:
            meta["apc_paid_sum_usd"] = agg_result.apc_paid_sum_usd.value

    if (
        hasattr(response, "aggregations")
        and "cited_by_count_sum" in response.aggregations
    ):
        meta["cited_by_count_sum"] = response.aggregations.cited_by_count_sum.value
    return meta


def format_group_by(response, params, index_name, fields_dict, connection='default'):
    group_by, include_unknown = parse_group_by(params["group_by"])
    group_by_data = get_group_by_results(
        group_by, include_unknown, params, index_name, fields_dict, response, connection
    )
    return group_by_data


def format_group_bys(response, params, index_name, fields_dict, connection='default'):
    group_bys_data = []

    for group_by_item in params["group_bys"]:
        group_by_item, include_unknown = parse_group_by(group_by_item)
        item_results = get_group_by_results(
            group_by_item, include_unknown, params, index_name, fields_dict, response, connection
        )
        group_bys_data.append({"group_by_key": group_by_item, "groups": item_results})

    return group_bys_data


def calculate_sample_or_default_count(params, response):
    count = response.hits.total.value
    if params.get("sample") and params["sample"] < count:
        return params["sample"]
    return count
