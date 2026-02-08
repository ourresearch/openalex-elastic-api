import settings
from core.exceptions import APIQueryParamsError


# Search parameter prefixes that are accepted via dot notation
SEARCH_PARAM_PREFIX = "search."
VALID_SEARCH_TYPES = ["search", "search.semantic", "search.exact"]


def validate_params(request):
    valid_params = [
        "apc_sum",
        "api-key",
        "api_key",
        "cited_by_count_sum",
        "cursor",
        "data_version",
        "data-version",
        "filter",
        "format",
        "include_xpac",
        "include-xpac",
        "group_by",
        "group-by",
        "group_bys",
        "group-bys",
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
        "warm",
    ]
    hidden_valid_params = ["bypass_cache"]
    for arg in request.args:
        # Accept any search.* param (dot notation)
        if arg.startswith(SEARCH_PARAM_PREFIX):
            if arg not in VALID_SEARCH_TYPES:
                raise APIQueryParamsError(
                    f"'{arg}' is not a valid search parameter. "
                    f"Valid search parameters are: {', '.join(VALID_SEARCH_TYPES)}."
                )
            continue
        if arg not in valid_params and arg not in hidden_valid_params:
            # Catch deprecated semantic=true parameter
            if arg == "semantic":
                raise APIQueryParamsError(
                    "The semantic=true parameter is deprecated. "
                    "Use search.semantic=your+query instead."
                )
            raise APIQueryParamsError(
                f"{arg} is not a valid parameter. Valid parameters are: {', '.join(valid_params)}."
            )
    data_version = request.args.get('data_version') or request.args.get('data-version')
    if data_version == '1':
        raise APIQueryParamsError(
            "data-version=1 is deprecated and no longer supported. "
            "Please remove the data-version parameter to use the current version of the API."
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
    # Collect all search params present in the request
    search_params_present = []
    if "search" in request.args:
        search_params_present.append("search")
    for arg in request.args:
        if arg.startswith(SEARCH_PARAM_PREFIX):
            search_params_present.append(arg)

    # Only one search param allowed per request
    if len(search_params_present) > 1:
        raise APIQueryParamsError(
            "Only one search parameter allowed per request. "
            f"You provided: {', '.join(search_params_present)}. "
            "Use search, search.semantic, or search.exact (not multiple)."
        )

    # Validate the search value (whichever param it came from)
    search_value = None
    for param in search_params_present:
        search_value = request.args.get(param)

    if search_value:
        if any(word.startswith("!") for word in search_value.split()):
            raise APIQueryParamsError(
                f"The search parameter does not support the ! operator. Problem value: {search_value}"
            )
        elif "|" in search_value:
            raise APIQueryParamsError(
                f"The search parameter does not support the | operator. Problem value: {search_value}"
            )


def validate_export_format(export_format):
    valid_formats = ["csv", "json", "xlsx"]
    if export_format and export_format.lower() not in valid_formats:
        raise APIQueryParamsError(f"Valid formats are {', '.join(valid_formats)}")


def validate_group_by(field, params):
    range_field_exceptions = [
        "apc_usd",
        "apc_list.value",
        "apc_list.value_usd",
        "apc_paid.value",
        "apc_paid.value_usd",
        "authors_count",
        "cited_by_count",
        "cited_by_percentile_year.min",
        "cited_by_percentile_year.max",
        "concepts_count",
        "domain.id",
        "end_year",
        "field.id",
        "fields.id",
        "hierarchy_level",
        "awards_count",
        "level",
        "countries_distinct_count",
        "institutions_distinct_count",
        "locations_count",
        "primary_topic.domain.id",
        "primary_topic.subfield.id",
        "primary_topic.field.id",
        "publication_year",
        "referenced_works_count",
        "start_year",
        "subfield.id",
        "subfields.id",
        "summary_stats.2yr_mean_citedness",
        "summary_stats.h_index",
        "summary_stats.i10_index",
        "topics.domain.id",
        "topics.subfield.id",
        "topics.field.id",
        "works_count",
    ]
    if (
        type(field).__name__ == "DateField"
        or type(field).__name__ == "DateTimeField"
        or (
            type(field).__name__ == "RangeField"
            and field.param not in range_field_exceptions
        )
        or type(field).__name__ == "SearchField"
    ):
        raise APIQueryParamsError("Cannot group by date, number, or search fields.")
    elif field.param == "referenced_works":
        raise APIQueryParamsError(
            "Group by referenced_works is not supported at this time."
        )
    elif field.param in settings.DO_NOT_GROUP_BY:
        raise APIQueryParamsError(f"Cannot group by {field.param}.")
    elif (
        field.param in settings.BOOLEAN_TEXT_FIELDS
        or field.param in settings.EXTERNAL_ID_FIELDS
        or type(field).__name__ == "BooleanField"
    ) and params.get("cursor"):
        raise APIQueryParamsError(
            "Cannot use cursor pagination when grouping fields that return true or false."
        )
