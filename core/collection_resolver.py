"""Resolve OpenAlex collection IDs into member-ID lists by calling openalex-users-api.

Labels are user-owned named collections of one entity type each. See oxjob #228
(collections-v1) for design notes. The `collection:` filter syntax in elastic-api
(`/works?filter=collection:collection-abc123`) resolves to a list of entity IDs via this
module, which then becomes a `terms` clause in the ES query.
"""
import logging
import re

import requests
from flask import g, request, has_request_context

import settings
from core.exceptions import (
    APIQueryParamsError,
    CollectionNotFoundError,
    CollectionResolutionUnavailableError,
    CollectionTooBigToFilterError,
)


logger = logging.getLogger(__name__)

# How long the one users-api call may take. It returns up to 300,000 IDs (~4 MB); the
# proxy gives the whole request 9 s.
HTTP_TIMEOUT = 8

# Live filter limits (oxjob #1527, charter plans/collections.md "Limits"). A collection
# holds up to 1,000,000 members, but as a filter its IDs travel with every request, so:
# author collections filter live up to 100,000 (author filters pull whole careers, so a
# bigger roster gives wrong answers, not just slow ones: the charter's Brazil case), and
# every other type up to 300,000, which covers every source (260,268) and institution
# (140,266). Works collections at 1M wait for the stamp (the next stage).
LIVE_FILTER_LIMIT = 300_000
LIVE_FILTER_LIMITS = {"authors": 100_000}

# Request-wide caps shared by EVERY path that resolves a collection (URL same-type,
# URL cross-type, OQL/OQO leaves, re-runs for custom group_by). Anyone can now
# reference a collection shared by link, logged in or not, and each distinct one
# costs a users-api call plus its IDs, so these bound one request's work
# (oxjob #646 security review H1; labels-v1 H2/H3 capped only the URL path).
# Callers also cap how many collection REFERENCES a query may hold
# (MAX_COLLECTION_REFERENCES_PER_REQUEST), since a repeated ID costs terms, not calls.
MAX_COLLECTIONS_PER_REQUEST = 5
MAX_COLLECTION_REFERENCES_PER_REQUEST = 5
MAX_RESOLVED_IDS_PER_REQUEST = LIVE_FILTER_LIMIT

# Public-facing message for any 503. Internal details (hostname, status code,
# JSON parse errors) go to the server log only — never to the response body
# (security review M4).
_UNAVAILABLE_MSG = "collection resolution temporarily unavailable"


def live_filter_limit(entity_type):
    return LIVE_FILTER_LIMITS.get(entity_type, LIVE_FILTER_LIMIT)


def too_big_message(entity_type, member_count):
    """What a filter by a collection over its live limit says instead of running."""
    limit = live_filter_limit(entity_type)
    if entity_type == "authors":
        return (
            f"Too big to filter live: this collection has {member_count:,} authors, and author "
            f"collections filter live up to {limit:,}. For a whole country or institution, use "
            "the Country or Institution filter. It counts by affiliation and is exact."
        )
    return (
        f"Too big to filter live: this collection has {member_count:,} {entity_type}, and "
        f"collections filter live up to {limit:,} members. It still holds and exports them."
    )


def resolve_collection(collection_id):
    """Look up a collection by ID and return (entity_type, [entity_ids]).

    One users-api call, `GET /collections/{id}/member-ids?max=...`, returns the type and
    every member ID (oxjob #1527; it used to page 1,000 IDs at a time, 50 calls for a
    50,000-member collection). Over the limit, users-api sends only the count.

    - Raises CollectionNotFoundError (404) when the caller can't read it:
      missing, deleted, or private to someone else (users-api answers 404 for all
      three; 401/403 are handled the same for safety). This replaced the old silent
      zero, which made a shared search link quietly return nothing (oxjob #646).
    - Raises CollectionTooBigToFilterError (400) over its type's live filter limit.
    - Raises CollectionResolutionUnavailableError on users-api 5xx / timeout /
      connection failure. The Flask error handler turns that into a 503.
    - Raises APIQueryParamsError if USERS_API_URL is not configured.
    """
    if not settings.USERS_API_URL:
        raise APIQueryParamsError(
            "collection: filter is not configured (USERS_API_URL unset)"
        )

    # One users-api call per distinct collection per request, however many times
    # the query (or a group_by re-run) names it.
    state = _request_state()
    if state is not None and collection_id in state["resolved"]:
        return state["resolved"][collection_id]
    if state is not None and len(state["resolved"]) >= MAX_COLLECTIONS_PER_REQUEST:
        raise APIQueryParamsError(
            f"A request can use at most {MAX_COLLECTIONS_PER_REQUEST} different collections."
        )

    base = settings.USERS_API_URL.rstrip("/")

    # Forward the current request's Authorization header so users-api can decide
    # access for THIS caller: the owner reads a private collection, anyone reads one
    # shared by link (oxjob #646). Without a request context (e.g. unit tests calling
    # this directly), forward nothing, which reads as a logged-out caller.
    auth_header = ""
    if has_request_context():
        auth_header = request.headers.get("Authorization", "") or ""
    fwd_headers = {"Authorization": auth_header} if auth_header else {}
    # Skip users-api's per-IP read limit: this traffic comes from Heroku's shared
    # egress IPs and is already metered per caller at the proxy. Grants no access.
    if settings.COLLECTION_RESOLVER_KEY:
        fwd_headers["X-Collection-Resolver-Key"] = settings.COLLECTION_RESOLVER_KEY

    url = f"{base}/collections/{collection_id}/member-ids"
    try:
        resp = requests.get(
            url,
            params={"max": LIVE_FILTER_LIMIT},
            headers=fwd_headers,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning(
            "collection resolver request failed for %s: %s", collection_id, e,
        )
        raise CollectionResolutionUnavailableError(_UNAVAILABLE_MSG)

    # No access, missing or deleted: one loud error, same for all, so probes
    # can't tell a private collection from a missing one.
    if resp.status_code in (401, 403, 404):
        raise CollectionNotFoundError(
            f"Collection {collection_id} not found."
        )

    # Anything other than 200 (including 5xx) is treated as users-api being
    # unavailable; the Flask error handler turns that into a 503.
    if resp.status_code != 200:
        logger.warning(
            "users-api %s resolving collection %s", resp.status_code, collection_id,
        )
        raise CollectionResolutionUnavailableError(_UNAVAILABLE_MSG)

    try:
        payload = resp.json()
    except ValueError as e:
        logger.warning(
            "users-api non-JSON response for collection %s: %s", collection_id, e,
        )
        raise CollectionResolutionUnavailableError(_UNAVAILABLE_MSG)

    entity_type = payload.get("entity_type")
    member_count = payload.get("member_count") or 0
    entity_ids = payload.get("member_ids")
    if entity_ids is None or member_count > live_filter_limit(entity_type):
        raise CollectionTooBigToFilterError(too_big_message(entity_type, member_count))

    if state is not None:
        state["ids"] += len(entity_ids)
        if state["ids"] > MAX_RESOLVED_IDS_PER_REQUEST:
            raise APIQueryParamsError(
                f"The collections in this request hold too many members to filter live "
                f"together (at most {MAX_RESOLVED_IDS_PER_REQUEST:,} in all)."
            )
        state["resolved"][collection_id] = (entity_type, entity_ids)
    return (entity_type, entity_ids)


# A collection's `id` is the URL `https://openalex.org/collections/col_x` (oxjob #1524),
# and like every OpenAlex ID it works wherever the short `col_x` does. One rewrite of
# the query string, before any view reads it, covers every reader: URL filters, the
# cross-type pre-pass, OQL and the URL->OQO parser. Raw or percent-encoded.
_COLLECTION_URL_IN_QUERY_RE = re.compile(
    r"(?:https?(?::|%3A)(?:/|%2F){1,2})?(?:www\.)?openalex\.org(?:/|%2F)collections(?:/|%2F)(?=col_)",
    re.IGNORECASE,
)


def short_collection_ids_in_query(query_string):
    """`filter=collection:https://openalex.org/collections/col_x` -> `filter=collection:col_x`."""
    if "collections" not in query_string:
        return query_string
    return _COLLECTION_URL_IN_QUERY_RE.sub("", query_string)


class CollectionUrlIdsInQuery:
    """WSGI middleware applying short_collection_ids_in_query to every request."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = environ.get("QUERY_STRING")
        if qs:
            environ["QUERY_STRING"] = short_collection_ids_in_query(qs)
        return self.wsgi_app(environ, start_response)


def _request_state():
    """Per-request memo and budget on flask.g, or None outside a request."""
    if not has_request_context():
        return None
    if not hasattr(g, "_collection_resolver"):
        g._collection_resolver = {"resolved": {}, "ids": 0}
    return g._collection_resolver


def check_collection_reference_count(count):
    """Raise if a query names collections more than the per-request cap allows."""
    if count > MAX_COLLECTION_REFERENCES_PER_REQUEST:
        raise APIQueryParamsError(
            f"A request can use at most {MAX_COLLECTION_REFERENCES_PER_REQUEST} "
            f"collection references."
        )
