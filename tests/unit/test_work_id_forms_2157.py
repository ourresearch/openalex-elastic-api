"""oxjob #2157: /works/<id> by arXiv id, bare DOI and upper-case scheme (DOI:, PMID:, PMCID:, MAG:) answered 404.
No ES: the view's query and its Lakebase key are captured. Run with --noconftest."""
import json
from unittest import mock

import pytest

from ids.utils import (arxiv_copy_urls, arxiv_doi, arxiv_form, is_bare_doi, lower_scheme, normalize_arxiv)


@pytest.mark.parametrize("value, want", [
    ("DOI:10.1038/nature12373", "doi:10.1038/nature12373"),
    ("Doi:10.1038/ABC", "doi:10.1038/ABC"),          # the value keeps its case
    ("PMID:35202565", "pmid:35202565"),
    ("PMCID:PMC8808747", "pmcid:PMC8808747"),
    ("MAG:2741809807", "mag:2741809807"),
    ("arXiv:2305.18290", "arxiv:2305.18290"),
    ("OpenAlex:W2741809807", "openalex:W2741809807"),
    ("https://doi.org/10.1/x", "https://doi.org/10.1/x"),  # a URL scheme is not an id scheme
    ("W2741809807", "W2741809807"),
    ("ORCID:0000-0002-1825-0097", "ORCID:0000-0002-1825-0097"),  # not a work id scheme
])
def test_lower_scheme(value, want):
    assert lower_scheme(value) == want


@pytest.mark.parametrize("value, want", [
    ("10.1038/nature12373", True), ("10.48550/arXiv.2305.18290", True), (" 10.1000/x", True),
    ("10.", False), ("10.12/x", False), ("2305.18290", False), ("W10.1038/x", False), ("x10.1038/x", False),
])
def test_is_bare_doi(value, want):
    assert is_bare_doi(value) is want


@pytest.mark.parametrize("value, want", [
    ("arxiv:2305.18290", "2305.18290"),
    ("arxiv:1706.03762v5", "1706.03762"),
    ("arxiv: 2305.18290", "2305.18290"),
    ("https://arxiv.org/abs/2305.18290", "2305.18290"),
    ("https:/arxiv.org/abs/2305.18290", "2305.18290"),  # the router collapses //
    ("http://arxiv.org/abs/1706.03762v7", "1706.03762"),
    ("https://arxiv.org/pdf/2305.18290v2.pdf", "2305.18290"),
    ("https://arxiv.org/pdf/2305.18290", "2305.18290"),
    ("arxiv.org/abs/1706.03762", "1706.03762"),
    ("https://www.arxiv.org/abs/1706.03762", "1706.03762"),
    ("https://export.arxiv.org/abs/1706.03762", "1706.03762"),
    ("https://arxiv.org/abs/2305.18290/", "2305.18290"),
    ("2305.18290", "2305.18290"),
    ("2305.18290v3", "2305.18290"),
    ("arxiv:0704.0001", "0704.0001"),
    ("arxiv:hep-th/9711200", "hep-th/9711200"),
    ("arXiv:cond-mat/0204273v2", "cond-mat/0204273"),
    ("https://arxiv.org/abs/hep-th/9711200v3", "hep-th/9711200"),
    ("arXiv:math.AG/0309136", "math/0309136"),     # the subject class is not part of the id
    ("arXiv:HEP-TH/9711200", "hep-th/9711200"),
])
def test_arxiv_forms_normalize(value, want):
    assert normalize_arxiv(arxiv_form(value)) == want


@pytest.mark.parametrize("value", ["arxiv:", "arxiv:notanid", "arxiv:2305.183", "arxiv:23051.8290",
                                   "https://arxiv.org/abs/"])
def test_malformed_arxiv_is_none(value):
    assert arxiv_form(value) is not None
    assert normalize_arxiv(arxiv_form(value)) is None


@pytest.mark.parametrize("value", ["https://doi.org/10.48550/arxiv.2305.18290", "doi:10.48550/arxiv.2305.18290",
                                   "10.48550/arxiv.2305.18290", "W2741809807", "pmid:123", "12345678",
                                   "2305.182", "123.45678", "https://pubmed.ncbi.nlm.nih.gov/1"])
def test_not_an_arxiv_form(value):
    assert arxiv_form(value) is None


def test_arxiv_doi_and_copy_urls():
    assert arxiv_doi("2305.18290") == "https://doi.org/10.48550/arxiv.2305.18290"
    urls = arxiv_copy_urls("2305.18290")
    # every arXiv page form seen on 100 random arXiv works (seed 2160, 11 Nov 2026)
    for u in ("https://doi.org/10.48550/arxiv.2305.18290", "https://doi.org/10.48550/arXiv.2305.18290",
              "http://arxiv.org/abs/2305.18290", "https://arxiv.org/abs/2305.18290", "https://arxiv.org/abs/2305.18290v2",
              "http://arxiv.org/abs/2305.18290v1", "https://arxiv.org/pdf/2305.18290", "https://arxiv.org/pdf/2305.18290.pdf",
              "https://arxiv.org/pdf/2305.18290v2", "http://arxiv.org/pdf/2305.18290"):
        assert u in urls
    assert len(urls) == len(set(urls))


# --- the view: which Lakebase key and which ES query each form builds ---

@pytest.fixture
def app_client(monkeypatch):
    for k, v in {"REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
                 "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
                 "USERS_DB_URL": "postgresql://u:p@localhost:5432/db",
                 "DATABASE_URL": "postgresql://u:p@localhost:5432/db", "JWT_SECRET_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    from app import create_app
    app = create_app("tests.settings")
    return app.test_client()


def _lookup(app_client, path, follow=True):
    """(status, Lakebase ext_id asked, ES query body) for one GET; both backends answer 'not found'."""
    seen = {"ext_id": None, "es": None}

    def fake_execute(self):
        seen["es"] = json.dumps(self.to_dict())
        return []

    def fake_ext(ext_id):
        seen["ext_id"] = ext_id
        return None

    with mock.patch("elasticsearch_dsl.Search.execute", fake_execute), \
            mock.patch("works.lakebase.should_route", return_value=True), \
            mock.patch("works.lakebase.get_work_doc_by_ext_id", fake_ext), \
            mock.patch("ids.views.redirect_if_merged", return_value=None):
        # follow: Werkzeug merges the // of a URL-form id with a redirect, as the live router does (oxjob #850)
        r = app_client.get(path, follow_redirects=follow)
    return r, seen["ext_id"], seen["es"]


ARXIV_DOI = "https://doi.org/10.48550/arxiv.2305.18290"


@pytest.mark.parametrize("path", [
    "/works/arxiv:2305.18290", "/works/arXiv:2305.18290", "/works/ARXIV:2305.18290v2",
    "/works/https://arxiv.org/abs/2305.18290", "/works/https://arxiv.org/pdf/2305.18290v2.pdf",
    "/works/arxiv.org/abs/2305.18290", "/works/2305.18290",
])
def test_arxiv_forms_look_up_arxivs_doi_then_its_pages(app_client, path):
    r, ext_id, es = _lookup(app_client, path)
    assert r.status_code == 404  # nothing found in the fakes
    assert ext_id == ARXIV_DOI   # Lakebase: the same key doi:10.48550/arxiv.<id> uses
    assert ARXIV_DOI in es and "http://arxiv.org/abs/2305.18290" in es  # ES: served DOI or an arXiv copy's page


@pytest.mark.parametrize("path, want", [
    ("/works/10.1038/nature12373", "https://doi.org/10.1038/nature12373"),
    ("/works/DOI:10.1038/nature12373", "https://doi.org/10.1038/nature12373"),
    ("/works/Doi:10.1038/NATURE12373", "https://doi.org/10.1038/nature12373"),
    ("/works/doi:10.1038/nature12373", "https://doi.org/10.1038/nature12373"),
    ("/works/HTTPS://DOI.ORG/10.1038/nature12373", "https://doi.org/10.1038/nature12373"),
    ("/works/PMID:35202565", "https://pubmed.ncbi.nlm.nih.gov/35202565"),
    ("/works/pmid:35202565", "https://pubmed.ncbi.nlm.nih.gov/35202565"),
])
def test_doi_and_pmid_forms_any_case(app_client, path, want):
    r, ext_id, es = _lookup(app_client, path)
    assert r.status_code == 404
    assert ext_id == want


def test_upper_case_pmcid_reaches_the_pmcid_query(app_client):
    r, ext_id, es = _lookup(app_client, "/works/PMCID:PMC8808747")
    assert r.status_code == 404
    assert "https://www.ncbi.nlm.nih.gov/pmc/articles/8808747" in es


@pytest.mark.parametrize("path", ["/works/MAG:2741809807", "/works/mag:2741809807"])
def test_mag_any_case_redirects_to_the_w_id(app_client, path):
    r, _, _ = _lookup(app_client, path, follow=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/works/W2741809807")


@pytest.mark.parametrize("path", ["/works/arxiv:", "/works/arxiv:notanid", "/works/10.", "/works/nonsense",
                                  "/works/https://arxiv.org/list/hep-th/new"])
def test_malformed_ids_404_without_a_query(app_client, path):
    r, ext_id, es = _lookup(app_client, path)
    assert r.status_code == 404
    assert ext_id is None and es is None


# --- the filter: doi: and pmid: values read the id out of any prefix (they silently matched 0) ---

def _filter_body(key, value):
    from elasticsearch_dsl import Search
    from core.filter import filter_records
    from works.fields import fields_dict as works_fields_dict
    return json.dumps(filter_records(works_fields_dict, [{key: value}], Search()).to_dict(), sort_keys=True)


@pytest.mark.parametrize("value", ["DOI:10.1038/nature12373", "doi:10.1038/NATURE12373", "http://dx.doi.org/10.1038/nature12373",
                                   "doi.org/10.1038/nature12373", "https://doi.org/10.1038/nature12373"])
def test_doi_filter_any_prefix_is_the_bare_doi(value):
    assert _filter_body("doi", value) == _filter_body("doi", "10.1038/nature12373")


def test_negated_doi_filter_with_prefix():
    assert _filter_body("doi", "!DOI:10.1038/nature12373") == _filter_body("doi", "!10.1038/nature12373")


@pytest.mark.parametrize("key", ["pmid", "ids.pmid"])
@pytest.mark.parametrize("value", ["PMID:35202565", "pmid:35202565"])
def test_pmid_filter_drops_the_prefix(key, value):
    assert _filter_body(key, value) == _filter_body(key, "35202565")


@pytest.mark.parametrize("value", ["2305.18290", "arXiv:2305.18290v2", "https://arxiv.org/abs/2305.18290",
                                   "arxiv.org/pdf/2305.18290.pdf"])
def test_arxiv_filter_is_the_arxiv_doi_filter(value):
    assert _filter_body("ids.arxiv", value) == _filter_body("doi", "10.48550/arxiv.2305.18290")


def test_arxiv_filter_old_style_and_negation():
    assert _filter_body("ids.arxiv", "hep-th/9711200") == _filter_body("doi", "10.48550/arxiv.hep-th/9711200")
    assert _filter_body("ids.arxiv", "!2305.18290") == _filter_body("doi", "!10.48550/arxiv.2305.18290")


@pytest.mark.parametrize("value", ["notanid", "null", "10.1038/nature12373"])
def test_arxiv_filter_bad_value_is_a_400(value):
    from core.exceptions import APIQueryParamsError
    with pytest.raises(APIQueryParamsError):
        _filter_body("ids.arxiv", value)


def test_doi_lookup_es_fallback_also_matches_a_location_doi(app_client):
    r, ext_id, es = _lookup(app_client, "/works/10.48550/arXiv.2305.18290")
    assert ext_id == ARXIV_DOI
    assert '"ids.doi": "%s"' % ARXIV_DOI in es and '"locations_full.doi.lower": "%s"' % ARXIV_DOI in es
