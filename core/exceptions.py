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


class CollectionNotFoundOrNotSharedError(APIError):
    """A `col_` reference the caller can't read: missing, deleted, or private to
    someone else. One message for all three, so a probe can't tell a private
    collection from a missing one (oxjob #646). Replaces the old silent zero."""
    code = 404
    description = "Collection doesn't exist or isn't shared"


class CollectionResolutionUnavailableError(APIError):
    code = 503
    description = "collection resolution unavailable"
