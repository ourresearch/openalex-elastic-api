from core.exceptions import APIQueryParamsError


def get_field(fields_dict, key):
    try:
        field = fields_dict[key]
        return field
    except KeyError:
        valid_fields = sorted(list(fields_dict.keys()))
        raise APIQueryParamsError(
            f"{key} is not a valid field. Valid fields are: {valid_fields}"
        )


def map_filter_params(param):
    if param:
        try:
            params = param.split(",")
            result = {k: v for k, v in (x.split(":") for x in params)}
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        result = None
    return result


def map_sort_params(param):
    if param:
        try:
            params = param.split(",")
            # parse params and set desc as default
            result = {
                k: v
                for k, v in (x.split(":") if ":" in x else (x, "asc") for x in params)
            }
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        result = None
    return result


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
