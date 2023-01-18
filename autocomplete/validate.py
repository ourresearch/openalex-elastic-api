from core.exceptions import APIQueryParamsError


def validate_entity_autocomplete_params(request):
    valid_params = ["q", "filter", "mailto", "search", "hide_zero", "author_hint"]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the entity autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )
    validate_author_hint(request)


def validate_full_autocomplete_params(request):
    valid_params = [
        "author_hint",
        "entity_type",
        "mailto",
        "q",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter for the full autocomplete endpoint. Valid parameters are: {', '.join(valid_params)}."
            )
    validate_author_hint(request)


def validate_author_hint(request):
    author_hint = request.args.get("author_hint")
    if author_hint and author_hint not in ["highly_cited_work", "institution"]:
        raise APIQueryParamsError(
            f"author_hint must be either 'highly_cited_work' or 'affiliation'. You entered {author_hint}."
        )
