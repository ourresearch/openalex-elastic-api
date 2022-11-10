from collections import OrderedDict

from elasticsearch_dsl import A, Q, Search

from core.exceptions import APIQueryParamsError


def shared_histogram_view(request, param, fields_dict, index_name):
    if param not in fields_dict:
        raise APIQueryParamsError(f"{param} is not a valid field")

    interval = request.args.get("interval") or 500
    min_doc_count = request.args.get("min_doc_count") or 15

    s = Search(index=index_name)
    s.aggs.bucket(
        "number_histogram",
        "histogram",
        field=param,
        interval=int(interval),
        min_doc_count=int(min_doc_count),
    )
    response = s.execute()
    buckets = response.aggregations.number_histogram.buckets

    # result
    result = OrderedDict()
    result["meta"] = {
        "count": len(buckets),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": len(buckets),
    }
    result["results"] = buckets
    return result
