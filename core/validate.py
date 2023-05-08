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
        "seed",
        "search",
        "select",
        "sort",
    ]
    for arg in request.args:
        if arg not in valid_params:
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter. Valid parameters are: {', '.join(valid_params)}."
            )
    if any(
        [
            "host_venue" in value or "alternate_host_venues" in value
            for value in request.args.values()
        ]
    ):
        raise APIQueryParamsError(
            "host_venue and alternate_host_venues are deprecated in favor of locations. "
            "Read more here: https://groups.google.com/g/openalex-users/c/rRf34GRr-Oo"
        )
    validate_filter_param(request)
    validate_select_param(request)
    validate_sample_param(request)
    validate_search_param(request)


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

    if "sample" in request.args and int(request.args.get("sample")) > 10000:
        raise APIQueryParamsError("Sample size must be less than or equal to 10,000.")

    if "sample" in request.args and "sort" in request.args:
        raise APIQueryParamsError("sample does not work with sort.")
    elif "seed" in request.args and "sample" not in request.args:
        raise APIQueryParamsError(
            "You must include the sample parameter when using a seed value."
        )
    elif "sample" in request.args and (
        "group-by" in request.args or "group_by" in request.args
    ):
        raise APIQueryParamsError("sample does not work with group_by.")

    if (
        "sample" in request.args
        and ("page" in request.args and int(request.args.get("page")) > 1)
        and "seed" not in request.args
    ):
        raise APIQueryParamsError(
            "A seed value is required when paginating through samples of results. "
            "Without a seed value, you may receive duplicate results between pages. Add a seed value like this: "
            "/works?sample=100&seed=123&page=2"
        )


def validate_search_param(request):
    if "search" in request.args and any(
        [word.startswith("!") for word in request.args.get("search").split()]
    ):
        raise APIQueryParamsError(
            f"The search parameter does not support the ! operator. Problem value: {request.args.get('search')}"
        )
    elif "search" in request.args and "|" in request.args.get("search"):
        raise APIQueryParamsError(
            f"The search parameter does not support the | operator. Problem value: {request.args.get('search')}"
        )


def validate_export_format(export_format):
    valid_formats = ["csv", "json", "xlsx"]
    if export_format and export_format.lower() not in valid_formats:
        raise APIQueryParamsError(f"Valid formats are {', '.join(valid_formats)}")
