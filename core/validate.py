from core.exceptions import APIQueryParamsError


def validate_params(request):
    valid_params = [
        "cursor",
        "filter",
        "format",
        "group_by",
        "group-by",
        "mailto",
        "page",
        "per_page",
        "per-page",
        "q",
        "search",
        "sort",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter. Valid parameters are: {', '.join(valid_params)}."
            )

    if request.url.count("?filter=") + request.url.count("&filter=") > 1:
        raise APIQueryParamsError(
            "Only one filter parameter is allowed. "
            "Your URL contains filters like: /works?filter=publication_year:2020&filter=is_open_access:true. "
            "Combine and separate filters with a comma, like: /works?filter=publication_year:2020,is_open_access:true."
        )


def validate_export_format(export_format):
    valid_formats = ["csv", "json", "xlsx"]
    if export_format and export_format.lower() not in valid_formats:
        raise APIQueryParamsError(f"Valid formats are {', '.join(valid_formats)}")
