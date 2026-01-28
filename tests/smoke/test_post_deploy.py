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

API_BASE = "https://api.openalex.org"
CONTENT_BASE = "https://content.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY")
TIMEOUT = 30  # seconds

# A known stable work ID for deterministic tests
KNOWN_WORK_ID = "W2741809807"  # "The state of OA" paper - unlikely to be deleted


class TestSmokeEndpoints:
    """Smoke tests for critical API endpoints."""

    def test_root_health_check(self):
        """Root endpoint should return 200 with version info."""
        response = requests.get(f"{API_BASE}/", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["msg"] == "Don't panic"

    def test_singleton_work(self):
        """Single work lookup should return 200 with work data."""
        response = requests.get(
            f"{API_BASE}/works/{KNOWN_WORK_ID}",
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == f"https://openalex.org/W2741809807"
        assert "title" in data
        assert "cited_by_count" in data

    def test_list_works(self):
        """Works list endpoint should return 200 with results."""
        response = requests.get(
            f"{API_BASE}/works",
            params={"per_page": 1},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["meta"]["count"] > 0

    def test_autocomplete(self):
        """Autocomplete should return 200 with suggestions."""
        response = requests.get(
            f"{API_BASE}/autocomplete/works",
            params={"q": "machine learning"},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0

    def test_filter_query(self):
        """Filtered query should return 200 with matching results."""
        response = requests.get(
            f"{API_BASE}/works",
            params={
                "filter": "publication_year:2023",
                "per_page": 1,
            },
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] > 0
        assert data["results"][0]["publication_year"] == 2023

    @pytest.mark.skipif(not API_KEY, reason="OPENALEX_API_KEY not set")
    def test_content_api_redirect(self):
        """Content API should return 302 redirect with valid API key."""
        response = requests.head(
            f"{CONTENT_BASE}/works/{KNOWN_WORK_ID}.pdf",
            params={"api_key": API_KEY},
            timeout=TIMEOUT,
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
        response = requests.get(
            f"{API_BASE}/authors",
            params={"per_page": 1},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        assert "results" in response.json()

    def test_institutions_list(self):
        """Institutions list should return 200."""
        response = requests.get(
            f"{API_BASE}/institutions",
            params={"per_page": 1},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        assert "results" in response.json()

    def test_sources_list(self):
        """Sources list should return 200."""
        response = requests.get(
            f"{API_BASE}/sources",
            params={"per_page": 1},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        assert "results" in response.json()
