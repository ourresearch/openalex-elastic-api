class APIError(Exception):
    """All custom API Exceptions"""

    pass


class APIPaginationError(APIError):
    code = 403
    description = "Pagination error."


class APIQueryParamsError(APIError):
    code = 403
    description = "Invalid query parameters error."


class APISearchError(APIError):
    code = 404
    description = "Search execution error."


class HighAuthorCountError(APIError):
    code = 403
    description = "This query produces too many authors. Reduce per-page to less than 10 to continue."
