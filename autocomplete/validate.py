from core.exceptions import APIQueryParamsError


def validate_entity_autocomplete_params(request):
    valid_params = [
        "q",
        "filter",
        "mailto",
        "search",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the entity autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )


def validate_full_autocomplete_params(request):
    valid_params = [
        "q",
        "mailto",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the full autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )
