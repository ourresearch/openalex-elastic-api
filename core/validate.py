from core.exceptions import APIPaginationError, APIQueryParamsError


def validate_params(filters, group_by, search):
    valid_filter_params = ["author_id", "issn", "ror_id", "year"]
    valid_group_by_params = ["author_id", "country", "issn", "open_access", "year"]
    valid_search_params = ["author", "journal_title", "publisher", "title"]

    if group_by and group_by not in valid_group_by_params:
        raise APIQueryParamsError(
            f"Invalid group by param provided. Valid params are {', '.join(valid_group_by_params)}."
        )

    # if fields:
    #     for filter_param in fields:
    #         if filter_param not in valid_filter_params:
    #             raise APIQueryParamsError(
    #                 f"Invalid filter param provided. Valid params are {', '.join(valid_filter_params)}."
    #             )

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
        and not search
    ):
        raise APIQueryParamsError(
            "Group by author ID or ISSN with year range query is not allowed."
        )

    # do not allow short title query with author_id group_by
    # title_length = 5
    # if (
    #     group_by
    #     and group_by == "author_id"
    #     and search
    #     and len(search_params) == 1
    #     and len(search_params["title"]) < title_length
    #     and not fields
    # ):
    #     raise APIQueryParamsError(
    #         f"Group by author ID with title search requires longer query (over {title_length -1} characters)."
    #     )
