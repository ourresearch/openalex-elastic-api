class APIError(Exception):
    """All custom API Exceptions"""

    pass


class APIPaginationError(APIError):
    """Error when per-page parameter is out of bounds."""

    code = 403
    description = "Pagination error."


class APIQueryParamsError(APIError):
    """Error when per-page parameter is out of bounds."""

    code = 403
    description = "Invalid query parameters error."
