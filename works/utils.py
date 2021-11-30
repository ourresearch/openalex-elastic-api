from works.exceptions import APIPaginationError


def map_query_params(param):
    if param:
        params = param.split(",")
        result = {k: v for k, v in (x.split(":") for x in params)}
    else:
        result = None
    return result


def validate_per_page(per_page):
    if per_page and per_page > 25 or per_page < 1:
        raise APIPaginationError("per-page parameter must be between 1 and 25")

    return per_page
