from elasticsearch_dsl import A, Search

from core.filter import filter_records
from core.search import full_search_query
from core.utils import map_filter_params


def shared_stats_view(request, fields_dict, index_name, stats_fields):
    s = Search(index=index_name)
    s = s.extra(size=0)

    # params
    filter_params = map_filter_params(request.args.get("filter"))
    search = request.args.get("search")

    # search
    if search and search != '""':
        search_query = full_search_query(index_name, search)
        s = s.filter(search_query)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s, sample=None)

    count = s.count()
    if count > 5000000:
        percents = [25, 50, 75, 90]
    else:
        percents = list(range(1, 100))

    for field in stats_fields:
        s.aggs.bucket(
            field + "_percentiles",
            A(
                "percentiles",
                field=field,
                percents=percents,
                tdigest={"compression": 25},
            ),
        )
        # aggregate the sum of cited_by_count
        s.aggs.bucket(field + "_sum", A("sum", field=field))
    response = s.execute()

    # set up results
    result = {
        "meta": {
            "count": count,
            "db_response_time_ms": response.took,
        },
        "stats": [],
    }
    if filter_params:
        result["meta"]["filters"] = filter_params
    if search:
        result["meta"]["search"] = search

    for field in stats_fields:
        percentiles = {}
        for key, value in (
            response.aggregations[field + "_percentiles"]
            .to_dict()
            .get("values", {})
            .items()
        ):
            key_display = int(float(key))
            value = int(value)
            percentiles[key_display] = value
        result["stats"].append(
            {
                "key": field,
                "percentiles": percentiles,
                "sum": response.aggregations[field + "_sum"].value,
            }
        )
    return result
