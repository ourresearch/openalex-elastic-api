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
    validate_filter_param(request)
    validate_select_param(request)
    validate_sample_param(request)
    validate_random_sort_param(request)


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
    random_sort = (
        request.args.get("sort") and request.args.get("sort").lower() == "random"
    )

    if "sample" in request.args:
        try:
            int(request.args.get("sample"))
        except ValueError:
            raise APIQueryParamsError("sample must be an integer.")

    if "sample" in request.args and int(request.args.get("sample")) > 10000:
        raise APIQueryParamsError("Sample size must be less than or equal to 10,000.")

    if "sample" in request.args and "sort" in request.args:
        raise APIQueryParamsError("sample does not work with sort.")
    elif "seed" in request.args and ("sample" not in request.args and not random_sort):
        raise APIQueryParamsError(
            "You must include the sample parameter or use a random sort when using a seed value."
        )
    elif "sample" in request.args and (
        "group-by" in request.args or "group_by" in request.args
    ):
        raise APIQueryParamsError("sample does not work with group_by.")
    elif ("sample" in request.args or random_sort) and "search" in request.args:
        raise APIQueryParamsError(
            "sample and random sort do not work with search right now."
        )

    if (
        ("sample" in request.args or random_sort)
        and (
            "page" in request.args
            and int(request.args.get("page")) > 1
            or "cursor" in request.args
        )
        and "seed" not in request.args
    ):
        raise APIQueryParamsError(
            "A seed value is required when paginating through samples or randomly sorted results. "
            "Without a seed value, you may receive duplicate results between pages. Add a seed value like: "
            "/works?sample=100&seed=123&page=2"
        )


def validate_random_sort_param(request):
    if "sort" in request.args and request.args.get("sort") == "random":
        if "group-by" in request.args or "group_by" in request.args:
            raise APIQueryParamsError("random sort does not work with group_by.")
        elif "sample" in request.args:
            raise APIQueryParamsError("random sort does not work with sample.")
        elif "search" in request.args:
            raise APIQueryParamsError("random sort does not work with search.")


def validate_export_format(export_format):
    valid_formats = ["csv", "json", "xlsx"]
    if export_format and export_format.lower() not in valid_formats:
        raise APIQueryParamsError(f"Valid formats are {', '.join(valid_formats)}")
