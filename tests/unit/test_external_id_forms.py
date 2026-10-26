"""oxjob #1884: the id-form helpers the singleton lookups use. No ES; runs under --noconftest."""
import pytest

from ids.utils import is_pubmed_url, normalize_wikidata, wikidata_forms, wikidata_query


def test_wikidata_query_terms_every_form_or_none():
    q = wikidata_query("ids.wikidata", "https://www.wikidata.org/wiki/Q42").to_dict()
    assert q == {"terms": {"ids.wikidata": wikidata_forms("Q42")}}
    assert wikidata_query("ids.wikidata", "wikidata:") is None


def test_wikidata_forms_cover_every_stored_form():
    forms = wikidata_forms("Q42")
    # forms seen in funders-v3, publishers-v6, institutions-v8 (26 Oct 2026)
    for stored in ("Q42", "https://www.wikidata.org/entity/Q42", "https://www.wikidata.org/wiki/Q42",
                   "https://wikidata.org/entity/Q42", "wikidata.org/wiki/Q42", "http://www.wikidata.org/entity/Q42"):
        assert stored in forms


@pytest.mark.parametrize(
    "value, want",
    [("wikidata:Q42", "Q42"), ("https://www.wikidata.org/wiki/q42", "Q42"), ("https:/www.wikidata.org/entity/Q42", "Q42"),
     ("wikidata:Q", None), ("wikidata:", None)],
)
def test_normalize_wikidata(value, want):
    assert normalize_wikidata(value) == want


@pytest.mark.parametrize(
    "value, want",
    [("https://pubmed.ncbi.nlm.nih.gov/29456894", True), ("https:/pubmed.ncbi.nlm.nih.gov/29456894", True),
     ("https://www.ncbi.nlm.nih.gov/pubmed/29456894", True), ("PUBMED.NCBI.NLM.NIH.GOV/1", True),
     ("https://doi.org/10.1/pubmed", False), ("pmid:29456894", False),
     ("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123", False)],
)
def test_is_pubmed_url(value, want):
    assert is_pubmed_url(value) is want
