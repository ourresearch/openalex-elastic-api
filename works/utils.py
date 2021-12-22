def convert_group_by(response, field):
    """
    Convert to key, doc_count dictionary
    """
    if not response.hits.hits:
        return []
    r = response.hits.hits[0]._source.to_dict()
    stats = r.get(field)
    result = [{"key": key, "doc_count": count} for key, count in stats.items()]
    result_sorted = sorted(
        result, key=lambda i: i["doc_count"], reverse=True
    )  # sort by count
    return result_sorted
