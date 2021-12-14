from works.exceptions import APIPaginationError, APIQueryParamsError


def validate_per_page(per_page):
    if per_page and per_page > 25 or per_page < 1:
        raise APIPaginationError("per-page parameter must be between 1 and 25")

    return per_page


def validate_result_size(page, per_page):
    valid_results_size = 10000
    if page * per_page > valid_results_size:
        raise APIPaginationError(
            "Maximum results size of 10,000 records is exceeded. Cursor pagination is required for records beyond 10,000 and is coming soon."
        )


def validate_params(filters, group_by, search_params):
    valid_filter_params = ["author_id", "issn", "ror_id", "year"]
    valid_group_by_params = ["author_id", "country", "issn", "open_access", "year"]
    valid_search_params = ["author", "journal_title", "publisher", "title"]

    if group_by and group_by not in valid_group_by_params:
        raise APIQueryParamsError(
            f"Invalid group by param provided. Valid params are {', '.join(valid_group_by_params)}."
        )

    if filters:
        for filter_param in filters:
            if filter_param not in valid_filter_params:
                raise APIQueryParamsError(
                    f"Invalid filter param provided. Valid params are {', '.join(valid_filter_params)}."
                )

    if search_params:
        for search_param in search_params:
            if search_param not in valid_search_params:
                raise APIQueryParamsError(
                    f"Invalid search param provided. Valid params are {', '.join(valid_search_params)}."
                )

    # do not allow query like:
    # /works?year>2000&group_by=author_id
    # /works?year>2000&group_by=issn
    if (
        group_by
        and filters
        and "year" in filters
        and (group_by == "author_id" or group_by == "issn")
        and ("<" in filters["year"] or ">" in filters["year"])
        and len(filters) == 1
        and not search_params
    ):
        raise APIQueryParamsError(
            "Group by author ID or ISSN with year range query is not allowed."
        )

    # do not allow short title query with author_id group_by
    title_length = 5
    if (
        group_by
        and group_by == "author_id"
        and search_params
        and "title" in search_params
        and len(search_params) == 1
        and len(search_params["title"]) < title_length
        and not filters
    ):
        raise APIQueryParamsError(
            f"Group by author ID with title search requires longer query (over {title_length -1} characters)."
        )
