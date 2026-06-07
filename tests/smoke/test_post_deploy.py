"""
Post-deploy smoke tests for OpenAlex API.

Run manually: pytest tests/smoke/test_post_deploy.py -v --noconftest
Run in CI: Set OPENALEX_API_KEY secret, triggered by GitHub Actions after deploy

These tests verify critical endpoints work after deployment.
They do NOT test edge cases - just basic "is it up and responding correctly?"
"""

import os
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_BASE = "https://api.openalex.org"
CONTENT_BASE = "https://content.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY")
# Polite-pool contact, used only when no API key is configured.
MAILTO = os.environ.get("OPENALEX_MAILTO", "team@ourresearch.org")
TIMEOUT = 30  # seconds

# A known stable work ID for deterministic tests
KNOWN_WORK_ID = "W2741809807"  # "The state of OA" paper - unlikely to be deleted


def _make_session():
    """Build a session that authenticates and retries transient failures.

    Without an API key these requests go through the *anonymous* rate limiter,
    which is keyed on client IP. CI runners share IPs with the rest of the
    world, so the smoke tests reliably trip it and get 429s. Sending the API
    key (post-Alice: `Authorization: Bearer <key>`) moves the requests onto the
    key's own, far higher, limit. The retry/backoff is defense-in-depth for any
    remaining transient 429/5xx during the rapid-fire test run.
    """
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,  # ~0s, 2s, 4s, 8s between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    if API_KEY:
        session.headers["Authorization"] = f"Bearer {API_KEY}"
    return session


SESSION = _make_session()


def api_get(url, params=None, **kwargs):
    """GET through the shared authenticated/retrying session."""
    params = dict(params or {})
    if not API_KEY:
        params.setdefault("mailto", MAILTO)
    kwargs.setdefault("timeout", TIMEOUT)
    return SESSION.get(url, params=params, **kwargs)


def api_head(url, params=None, **kwargs):
    """HEAD through the shared authenticated/retrying session."""
    params = dict(params or {})
    if not API_KEY:
        params.setdefault("mailto", MAILTO)
    kwargs.setdefault("timeout", TIMEOUT)
    return SESSION.head(url, params=params, **kwargs)


class TestSmokeEndpoints:
    """Smoke tests for critical API endpoints."""

    def test_root_health_check(self):
        """Root endpoint should return 200 with version info."""
        response = api_get(f"{API_BASE}/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["msg"] == "Don't panic"

    def test_singleton_work(self):
        """Single work lookup should return 200 with work data."""
        response = api_get(f"{API_BASE}/works/{KNOWN_WORK_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == f"https://openalex.org/W2741809807"
        assert "title" in data
        assert "cited_by_count" in data

    def test_list_works(self):
        """Works list endpoint should return 200 with results."""
        response = api_get(f"{API_BASE}/works", params={"per_page": 1})
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["meta"]["count"] > 0

    def test_autocomplete(self):
        """Autocomplete should return 200 with suggestions."""
        response = api_get(
            f"{API_BASE}/autocomplete/works",
            params={"q": "machine learning"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0

    def test_filter_query(self):
        """Filtered query should return 200 with matching results."""
        response = api_get(
            f"{API_BASE}/works",
            params={
                "filter": "publication_year:2023",
                "per_page": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] > 0
        assert data["results"][0]["publication_year"] == 2023

    @pytest.mark.skipif(not API_KEY, reason="OPENALEX_API_KEY not set")
    def test_content_api_redirect(self):
        """Content API should return 302 redirect with valid API key."""
        response = api_head(
            f"{CONTENT_BASE}/works/{KNOWN_WORK_ID}.pdf",
            params={"api_key": API_KEY},
            allow_redirects=False,
        )
        # 302 = redirect to R2, 404 = work doesn't have PDF (acceptable)
        assert response.status_code in [302, 404], (
            f"Expected 302 or 404, got {response.status_code}"
        )


class TestSmokeOtherEntities:
    """Smoke tests for non-works entity endpoints."""

    def test_authors_list(self):
        """Authors list should return 200."""
        response = api_get(f"{API_BASE}/authors", params={"per_page": 1})
        assert response.status_code == 200
        assert "results" in response.json()

    def test_institutions_list(self):
        """Institutions list should return 200."""
        response = api_get(f"{API_BASE}/institutions", params={"per_page": 1})
        assert response.status_code == 200
        assert "results" in response.json()

    def test_sources_list(self):
        """Sources list should return 200."""
        response = api_get(f"{API_BASE}/sources", params={"per_page": 1})
        assert response.status_code == 200
        assert "results" in response.json()
