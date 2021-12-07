def map_query_params(param):
    if param:
        params = param.split(",")
        result = {k: v for k, v in (x.split(":") for x in params)}
    else:
        result = None
    return result


def convert_author_group_by(response):
    """
    Convert to key, doc_count dictionary
    """
    r = response.hits.hits[0]._source.to_dict()
    author_stats = r.get("author_id")
    result = [{"key": key, "doc_count": count} for key, count in author_stats.items()]
    result_sorted = sorted(
        result, key=lambda i: i["doc_count"], reverse=True
    )  # sort by count
    return result_sorted
