"""
Functional smoke tests for content_urls feature.

These tests hit the live production API to verify:
1. The content_urls field appears in work objects when has_content flags are set
2. The URLs are correctly formatted
3. The URLs actually work and return content

Run with: pytest tests/acceptance/test_content_urls.py -v
"""

import pytest
import requests

API_BASE = "https://api.openalex.org"


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
        expected_pdf_url = f"https://api.openalex.org/content/{work_id}/pdf"
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
        expected_grobid_url = f"https://api.openalex.org/content/{work_id}/grobid-xml"
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

    def test_pdf_url_returns_content(self):
        """The PDF content URL should actually return PDF content."""
        # First, find a work with PDF content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.pdf:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] > 0

        work = data["results"][0]
        pdf_url = work["content_urls"]["pdf"]

        # Fetch the PDF (use HEAD to check without downloading full file)
        pdf_response = requests.head(pdf_url, timeout=30, allow_redirects=True)

        # Should return 200 or redirect to S3/storage
        assert pdf_response.status_code in [200, 302, 307], (
            f"PDF URL should be accessible, got {pdf_response.status_code}"
        )

        # If 200, verify content type
        if pdf_response.status_code == 200:
            content_type = pdf_response.headers.get("Content-Type", "")
            assert "pdf" in content_type.lower() or "octet-stream" in content_type.lower(), (
                f"Expected PDF content type, got {content_type}"
            )

    def test_grobid_xml_url_returns_content(self):
        """The grobid_xml content URL should actually return XML content."""
        # First, find a work with grobid_xml content
        response = requests.get(
            f"{API_BASE}/works",
            params={"filter": "has_content.grobid_xml:true", "per-page": 1},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["count"] > 0

        work = data["results"][0]
        grobid_url = work["content_urls"]["grobid_xml"]

        # Fetch the XML (use HEAD to check without downloading full file)
        xml_response = requests.head(grobid_url, timeout=30, allow_redirects=True)

        # Should return 200 or redirect to S3/storage
        assert xml_response.status_code in [200, 302, 307], (
            f"Grobid XML URL should be accessible, got {xml_response.status_code}"
        )

        # If 200, verify content type
        if xml_response.status_code == 200:
            content_type = xml_response.headers.get("Content-Type", "")
            assert "xml" in content_type.lower() or "octet-stream" in content_type.lower(), (
                f"Expected XML content type, got {content_type}"
            )

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
