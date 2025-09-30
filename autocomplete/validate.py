from core.exceptions import APIQueryParamsError


def validate_entity_autocomplete_params(request):
    valid_params = ["q", "filter", "mailto", "search", "hide_zero", "author_hint", "data_version", "data-version"]
    for arg in request.args:
        if arg not in valid_params and arg != 'bypass_cache':
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the entity autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )


def validate_full_autocomplete_params(request):
    valid_params = [
        "author_hint",
        "entity_type",
        "hide_works",
        "mailto",
        "q",
        "data_version",
        "data-version",
    ]
    for arg in request.args:
        if arg not in valid_params and arg != 'bypass_cache':
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the full autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )
