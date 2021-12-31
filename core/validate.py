from core.exceptions import APIQueryParamsError


def validate_params(request):
    valid_params = [
        "filter",
        "group_by",
        "group-by-size",
        "mailto",
        "page",
        "per-page",
        "sort",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter. Valid parameters are: {', '.join(valid_params)}."
            )
