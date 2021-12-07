def map_query_params(param):
    if param:
        params = param.split(",")
        result = {k: v for k, v in (x.split(":") for x in params)}
    else:
        result = None
    return result
