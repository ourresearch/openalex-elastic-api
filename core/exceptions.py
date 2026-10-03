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


class CollectionNotFoundError(APIError):
    """A `col_` reference the caller can't read: missing, deleted, or private to
    someone else. One message for all three, so a probe can't tell a private
    collection from a missing one (oxjob #646). Replaces the old silent zero."""
    code = 404
    description = "Collection not found"
    # Stable machine code, the same string users-api returns (oxjob #646).
    error_code = "collection_not_found"


class CollectionTooBigToFilterError(APIError):
    """A collection with more members than a live filter takes (oxjob #1527): author
    collections over 100,000, any other over 300,000. It still holds and exports its
    members; only filtering by it is refused, with a message saying what to do instead."""
    code = 400
    description = "Collection too big to filter"
    error_code = "collection_too_big_to_filter"


class CollectionResolutionUnavailableError(APIError):
    code = 503
    description = "collection resolution unavailable"
