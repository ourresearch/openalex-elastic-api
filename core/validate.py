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
        "sample",
        "sample_seed",
        "search",
        "select",
        "sort",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter. Valid parameters are: {', '.join(valid_params)}."
            )
    validate_filter_param(request)
    validate_select_param(request)
    validate_sample_param(request)


def validate_filter_param(request):
    if request.url.count("?filter=") + request.url.count("&filter=") > 1:
        raise APIQueryParamsError(
            "Only one filter parameter is allowed. "
            "Your URL contains filters like: /works?filter=publication_year:2020&filter=is_open_access:true. "
            "Combine and separate filters with a comma, like: /works?filter=publication_year:2020,is_open_access:true."
        )


def validate_select_param(request):
    if (
        "group_by" in request.args or "group-by" in request.args
    ) and "select" in request.args:
        raise APIQueryParamsError("select does not work with group_by.")


def validate_sample_param(request):
    if "sample" in request.args:
        try:
            int(request.args.get("sample"))
        except ValueError:
            raise APIQueryParamsError("sample must be an integer.")

    if "sample" in request.args and "sort" in request.args:
        raise APIQueryParamsError("sample does not work with sort.")
    elif "sample_seed" in request.args and "sample" not in request.args:
        raise APIQueryParamsError(
            "You must include the sample parameter when using sample_seed."
        )
    elif "sample" in request.args and (
        "group-by" in request.args or "group_by" in request.args
    ):
        raise APIQueryParamsError("sample does not work with group_by.")
    elif "sample" in request.args and "search" in request.args:
        raise APIQueryParamsError("sample does not work with search right now.")


def validate_export_format(export_format):
    valid_formats = ["csv", "json", "xlsx"]
    if export_format and export_format.lower() not in valid_formats:
        raise APIQueryParamsError(f"Valid formats are {', '.join(valid_formats)}")
