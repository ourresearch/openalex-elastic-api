class APIError(Exception):
    """All custom API Exceptions"""

    pass


class APIPaginationError(APIError):
    """Error when per-page parameter is out of bounds."""

    code = 403
    description = "pagination error"
