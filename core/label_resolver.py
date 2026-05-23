"""Resolve OpenAlex label IDs into entity-ID lists by calling openalex-users-api.

Labels are user-owned named collections of one entity type each. See oxjob #228
(labels-v1) for design notes. The `label:` filter syntax in elastic-api
(`/works?filter=label:label-abc123`) resolves to a list of entity IDs via this
module, which then becomes a `terms` clause in the ES query.
"""
import requests

import settings
from core.exceptions import APIQueryParamsError, LabelResolutionUnavailableError


PER_PAGE = 200
HTTP_TIMEOUT = 5


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

    while True:
        url = f"{base}/labels/{label_id}/entities"
        try:
            resp = requests.get(
                url,
                params={"page": page, "per_page": PER_PAGE},
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            raise LabelResolutionUnavailableError(str(e))

        if resp.status_code == 404:
            return (None, [])

        # Anything other than 200 (including 5xx) is treated as users-api being
        # unavailable; the Flask error handler turns that into a 503.
        if resp.status_code != 200:
            raise LabelResolutionUnavailableError(
                f"users-api {resp.status_code} resolving label {label_id}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise LabelResolutionUnavailableError(
                f"users-api non-JSON response for label {label_id}: {e}"
            )

        label = payload.get("label") or {}
        entity_type = label.get("entity_type") or entity_type
        entity_ids.extend(payload.get("entity_ids") or [])

        meta = payload.get("meta") or {}
        total_pages = meta.get("total_pages") or 1
        if page >= total_pages:
            break
        page += 1

    return (entity_type, entity_ids)
