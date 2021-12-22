from core.exceptions import APIQueryParamsError


def map_query_params(param):
    if param:
        try:
            params = param.split(",")
            result = {k: v for k, v in (x.split(":") for x in params)}
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        result = None
    return result
