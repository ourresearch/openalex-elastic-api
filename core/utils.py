import re

from core.exceptions import APIQueryParamsError


def get_field(fields_dict, key):
    try:
        field = fields_dict[key]
        return field
    except KeyError:
        valid_fields = sorted(list(fields_dict.keys()))
        raise APIQueryParamsError(
            f"{key} is not a valid field. Valid fields are underscore or hyphenated versions of: {', '.join(valid_fields)}"
        )


def map_filter_params(filter_params):
    """
    Split filter params by comma, then map to a dictionary based on key:value.
    """
    if filter_params:
        try:
            result = {}
            params = re.split(
                ",(?=[^,]+?:)", filter_params
            )  # split by comma but ignore within []
            for param in params:
                key, value = re.split(
                    ":(?!//)", param
                )  # split by colon but ignore colon within URL
                key = key.replace("-", "_")  # convert key to underscore
                result[key] = value
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        result = None
    return result


def map_sort_params(param):
    """
    Split sort params by comma, then map to a dictionary based on key:value.
    Assign default value of "asc" if no value specificed after the colon.
    """
    if param:
        try:
            result = {}
            params = param.split(",")
            # parse params and set asc as default
            for param in params:
                key, value = param.split(":") if ":" in param else (param, "asc")
                key = key.replace("-", "_")
                result[key] = value
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


def set_number_param(request, param, default):
    """
    Tries to get a number param with hyphen or underscore. Returns an error if not a number.
    """
    result = request.args.get(param) or request.args.get(param.replace("-", "_"))
    if result:
        try:
            result = int(result)
        except ValueError:
            raise APIQueryParamsError(f"Param {param} must be a number.")
    else:
        result = default
    return result
