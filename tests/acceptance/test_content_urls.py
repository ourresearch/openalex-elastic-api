"""
Functional smoke tests for content_urls feature.

These tests hit the live production API to verify:
1. The content_urls field appears in work objects when has_content flags are set
2. The URLs are correctly formatted
3. The URLs actually work and return content (when API key is provided)

Run with: pytest tests/acceptance/test_content_urls.py -v --noconftest

To test actual downloads, set OPENALEX_API_KEY environment variable:
  OPENALEX_API_KEY=your_key pytest tests/acceptance/test_content_urls.py -v --noconftest
"""

import os

import pytest
import requests

API_BASE = "https://api.openalex.org"
CONTENT_BASE = "https://content.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY")


class TestContentUrls:
    """Smoke tests for content_urls feature."""

    def test_content_urls_present_when_has_pdf(self):
        """Works with has_content.pdf=true should have content_urls.pdf."""
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["meta"]["count"] > 0, "Should find works with PDF content"
        work = data["results"][0]

        # Verify has_content structure
        assert work.get("has_content") is not None
        assert work["has_content"]["pdf"] is True

        # Verify content_urls structure
        assert work.get("content_urls") is not None, "content_urls should be present"
        assert "pdf" in work["content_urls"], "content_urls should have pdf key"

        # Verify URL format
        work_id = work["id"].split("/")[-1]
        expected_pdf_url = f"https://content.openalex.org/works/{work_id}.pdf"
        assert work["content_urls"]["pdf"] == expected_pdf_url

    def test_content_urls_present_when_has_grobid_xml(self):
        """Works with has_content.grobid_xml=true should have content_urls.grobid_xml."""
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.grobid_xml:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["meta"]["count"] > 0, "Should find works with grobid_xml content"
        work = data["results"][0]

        # Verify has_content structure
        assert work.get("has_content") is not None
        assert work["has_content"]["grobid_xml"] is True

        # Verify content_urls structure
        assert work.get("content_urls") is not None, "content_urls should be present"
        assert "grobid_xml" in work["content_urls"], "content_urls should have grobid_xml key"

        # Verify URL format
        work_id = work["id"].split("/")[-1]
        expected_grobid_url = f"https://content.openalex.org/works/{work_id}.grobid-xml"
        assert work["content_urls"]["grobid_xml"] == expected_grobid_url

    def test_content_urls_null_when_no_content(self):
        """Works without content should have content_urls=null."""
        response = requests.get(
            f"{API_BASE}/works",
            params={
                "filter": "has_content.pdf:false,has_content.grobid_xml:false",
                "per-page": 1,
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()

        if data["meta"]["count"] > 0:
            work = data["results"][0]
            # content_urls should be null (not an empty object)
            assert work.get("content_urls") is None

    def test_single_work_endpoint_has_content_urls(self):
        """Single work endpoint should also include content_urls."""
        # First find a work ID with content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        work_id = response.json()["results"][0]["id"].split("/")[-1]

        # Fetch single work
        single_response = requests.get(f"{API_BASE}/works/{work_id}", timeout=30)
        assert single_response.status_code == 200

        work = single_response.json()
        assert work.get("content_urls") is not None
        assert "pdf" in work["content_urls"]

    def test_pdf_url_requires_api_key(self):
        """PDF download without API key should return 401."""
        # First, find a work with PDF content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        work = response.json()["results"][0]
        pdf_url = work["content_urls"]["pdf"]

        # Try to fetch without API key - should get 401
        pdf_response = requests.head(pdf_url, timeout=30, allow_redirects=False)
        assert pdf_response.status_code == 401, (
            f"Expected 401 without API key, got {pdf_response.status_code}"
        )

    @pytest.mark.skipif(not API_KEY, reason="OPENALEX_API_KEY not set")
    def test_pdf_url_returns_content_with_api_key(self):
        """The PDF content URL should return content when API key is provided."""
        # First, find a work with PDF content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        work = response.json()["results"][0]
        pdf_url = work["content_urls"]["pdf"]

        # Fetch with API key
        pdf_response = requests.head(
            pdf_url,
            params={"api_key": API_KEY},
            timeout=30,
            allow_redirects=False,
        )

        # Should return 302 redirect to R2 signed URL
        assert pdf_response.status_code == 302, (
            f"Expected 302 redirect with API key, got {pdf_response.status_code}"
        )
        assert "Location" in pdf_response.headers

    @pytest.mark.skipif(not API_KEY, reason="OPENALEX_API_KEY not set")
    def test_grobid_xml_url_returns_content_with_api_key(self):
        """The grobid_xml content URL should return content when API key is provided."""
        # First, find a work with grobid_xml content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.grobid_xml:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        work = response.json()["results"][0]
        grobid_url = work["content_urls"]["grobid_xml"]

        # Fetch with API key
        xml_response = requests.head(
            grobid_url,
            params={"api_key": API_KEY},
            timeout=30,
            allow_redirects=False,
        )

        # Should return 302 redirect to R2 signed URL
        assert xml_response.status_code == 302, (
            f"Expected 302 redirect with API key, got {xml_response.status_code}"
        )
        assert "Location" in xml_response.headers

    @pytest.mark.skipif(not API_KEY, reason="OPENALEX_API_KEY not set")
    def test_pdf_download_full(self):
        """Actually download PDF content and verify it's valid."""
        # Find a work with PDF content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        work = response.json()["results"][0]
        pdf_url = work["content_urls"]["pdf"]

        # Download first 1KB to verify it's a PDF
        pdf_response = requests.get(
            pdf_url,
            params={"api_key": API_KEY},
            timeout=30,
            stream=True,
        )

        # Should get 200 after following redirect
        assert pdf_response.status_code == 200

        # Read first 1KB
        content = pdf_response.raw.read(1024)
        pdf_response.close()

        # PDF files start with %PDF
        assert content.startswith(b"%PDF"), "Downloaded content should be a valid PDF"
