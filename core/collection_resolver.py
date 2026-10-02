"""Resolve OpenAlex collection IDs into entity-ID lists by calling openalex-users-api.

Labels are user-owned named collections of one entity type each. See oxjob #228
(collections-v1) for design notes. The `collection:` filter syntax in elastic-api
(`/works?filter=collection:collection-abc123`) resolves to a list of entity IDs via this
module, which then becomes a `terms` clause in the ES query.
"""
import logging

import requests
from flask import g, request, has_request_context

import settings
from core.exceptions import (
    APIQueryParamsError,
    CollectionNotFoundOrNotSharedError,
    CollectionResolutionUnavailableError,
)


logger = logging.getLogger(__name__)

# Matches the per-collection cap in openalex-users-api (MAX_ENTITIES_PER_COLLECTION
# = 1000), so a full at-cap collection resolves in a single round-trip. users-api
# accepts up to 1000 since the matching deploy on 2026-05-29 (commit 03b481a).
# If users-api silently caps lower, the loop below handles it by paginating —
# correctness is unaffected, only latency.
PER_PAGE = 1000
HTTP_TIMEOUT = 5

# Request-wide caps shared by EVERY path that resolves a collection (URL same-type,
# URL cross-type, OQL/OQO leaves, re-runs for custom group_by). Anyone can now
# reference a collection shared by link, logged in or not, and each distinct one
# costs a users-api call plus up to 1,000 terms, so these bound one request's work
# (oxjob #646 security review H1; labels-v1 H2/H3 capped only the URL path).
# Callers also cap how many collection REFERENCES a query may hold
# (MAX_COLLECTION_REFERENCES_PER_REQUEST), since a repeated ID costs terms, not calls.
MAX_COLLECTIONS_PER_REQUEST = 5
MAX_COLLECTION_REFERENCES_PER_REQUEST = 5
MAX_RESOLVED_IDS_PER_REQUEST = 10_000

# Public-facing message for any 503. Internal details (hostname, status code,
# JSON parse errors) go to the server log only — never to the response body
# (security review M4).
_UNAVAILABLE_MSG = "collection resolution temporarily unavailable"


def resolve_collection(collection_id):
    """Look up a collection by ID and return (entity_type, [entity_ids]).

    - Raises CollectionNotFoundOrNotSharedError (404) when the caller can't read it:
      missing, deleted, or private to someone else (users-api answers 404 for all
      three; 401/403 are handled the same for safety). This replaced the old silent
      zero, which made a shared search link quietly return nothing (oxjob #646).
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
    entity_ids = []
    entity_type = None
    page = 1

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

    while True:
        url = f"{base}/collections/{collection_id}/entities"
        try:
            resp = requests.get(
                url,
                params={"page": page, "per_page": PER_PAGE},
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
            raise CollectionNotFoundOrNotSharedError(
                f"Collection {collection_id} not found or not shared."
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

        collection = payload.get("collection") or {}
        entity_type = collection.get("entity_type") or entity_type
        entity_ids.extend(payload.get("entity_ids") or [])

        meta = payload.get("meta") or {}
        total_pages = meta.get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1

    if state is not None:
        state["ids"] += len(entity_ids)
        if state["ids"] > MAX_RESOLVED_IDS_PER_REQUEST:
            raise APIQueryParamsError(
                f"The collections in this request hold too many entities "
                f"(max {MAX_RESOLVED_IDS_PER_REQUEST:,} in all)."
            )
        state["resolved"][collection_id] = (entity_type, entity_ids)
    return (entity_type, entity_ids)


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
