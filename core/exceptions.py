class APIError(Exception):
    """All custom API Exceptions"""

    pass


class APIPaginationError(APIError):
    code = 400
    description = "Pagination error."


class APIQueryParamsError(APIError):
    code = 400
    description = "Invalid query parameters error."


class APISearchError(APIError):
    code = 404
    description = "Search execution error."


class HighAuthorCountError(APIError):
    code = 400
    description = "High author count limitation."
