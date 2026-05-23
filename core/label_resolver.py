"""Resolve OpenAlex label IDs into entity-ID lists by calling openalex-users-api.

Labels are user-owned named collections of one entity type each. See oxjob #228
(labels-v1) for design notes. The `label:` filter syntax in elastic-api
(`/works?filter=label:label-abc123`) resolves to a list of entity IDs via this
module, which then becomes a `terms` clause in the ES query.
"""
import logging

import requests
from flask import request, has_request_context

import settings
from core.exceptions import APIQueryParamsError, LabelResolutionUnavailableError


logger = logging.getLogger(__name__)

PER_PAGE = 200
HTTP_TIMEOUT = 5

# Public-facing message for any 503. Internal details (hostname, status code,
# JSON parse errors) go to the server log only — never to the response body
# (security review M4).
_UNAVAILABLE_MSG = "label resolution temporarily unavailable"


def resolve_label(label_id):
    """Look up a label by ID and return (entity_type, [entity_ids]).

    - Returns (None, []) for unknown / deleted labels (404 from users-api) so
      filter callers can silently match zero results (spec: "Empty / nonexistent
      / deleted label: silently matches 0 results. No error.").
    - Raises LabelResolutionUnavailableError on users-api 5xx / timeout /
      connection failure. The Flask error handler turns that into a 503.
    - Raises APIQueryParamsError if USERS_API_URL is not configured.
    """
    if not settings.USERS_API_URL:
        raise APIQueryParamsError(
            "label: filter is not configured (USERS_API_URL unset)"
        )

    base = settings.USERS_API_URL.rstrip("/")
    entity_ids = []
    entity_type = None
    page = 1

    # Labels v1.1 (oxjob #228, QA-040) made labels owner+admin-only. Forward
    # the current request's Authorization header so users-api can authenticate
    # the user (JWT for the GUI path, OpenAlex API key for the API path) and
    # enforce the owner check. Without a request context (e.g. unit tests
    # calling this directly), forward nothing — users-api will 401 → silent
    # zero, same as an unauthenticated user.
    auth_header = ""
    if has_request_context():
        auth_header = request.headers.get("Authorization", "") or ""
    fwd_headers = {"Authorization": auth_header} if auth_header else {}

    while True:
        url = f"{base}/labels/{label_id}/entities"
        try:
            resp = requests.get(
                url,
                params={"page": page, "per_page": PER_PAGE},
                headers=fwd_headers,
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.warning(
                "label resolver request failed for %s: %s", label_id, e,
            )
            raise LabelResolutionUnavailableError(_UNAVAILABLE_MSG)

        # 401 / 403 = caller has no access to this label; treat as a missing
        # label so the filter silently matches zero. Same envelope as 404.
        # (Avoids leaking the existence of private labels via a different
        # error code to anon vs. authenticated probes.)
        if resp.status_code in (401, 403, 404):
            return (None, [])

        # Anything other than 200 (including 5xx) is treated as users-api being
        # unavailable; the Flask error handler turns that into a 503.
        if resp.status_code != 200:
            logger.warning(
                "users-api %s resolving label %s", resp.status_code, label_id,
            )
            raise LabelResolutionUnavailableError(_UNAVAILABLE_MSG)

        try:
            payload = resp.json()
        except ValueError as e:
            logger.warning(
                "users-api non-JSON response for label %s: %s", label_id, e,
            )
            raise LabelResolutionUnavailableError(_UNAVAILABLE_MSG)

        label = payload.get("label") or {}
        entity_type = label.get("entity_type") or entity_type
        entity_ids.extend(payload.get("entity_ids") or [])

        meta = payload.get("meta") or {}
        total_pages = meta.get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1

    return (entity_type, entity_ids)
