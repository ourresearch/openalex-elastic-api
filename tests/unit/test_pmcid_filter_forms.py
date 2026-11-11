"""oxjob #1862: works serve ids.pmcid in the legacy digits form (https://www.ncbi.nlm.nih.gov/pmc/articles/1078728),
which /works/pmcid: already builds. The pmcid / ids.pmcid filters must reach that form from every way users write a
PMCID: PMC1078728, 1078728, a version suffix, and either NCBI URL. Query-DSL only (no ES, no app): run with --noconftest."""
import json

import pytest
from elasticsearch_dsl import Search

from core.filter import filter_records
from works.fields import fields_dict as works_fields_dict

SERVED = "https://www.ncbi.nlm.nih.gov/pmc/articles/1078728"
HELD_PMC = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1078728/"


def _body(filters):
    return json.dumps(filter_records(works_fields_dict, filters, Search()).to_dict())


@pytest.mark.parametrize("param", ["pmcid", "ids.pmcid"])
@pytest.mark.parametrize("value", [
    "PMC1078728",
    "pmc1078728",
    "1078728",
    "PMC1078728.2",
    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1078728",
    "https://www.ncbi.nlm.nih.gov/pmc/articles/1078728",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC1078728/",
])
def test_every_pmcid_form_reaches_the_served_form(param, value):
    body = _body([{param: value}])
    assert SERVED in body, body
    # the PMC-prefixed form appears only as a PMC copy's landing page (oxjob #2155), never on ids.pmcid
    assert body.replace(HELD_PMC, "").count("PMC1078728") == 0, body


def test_or_of_pmcids():
    body = _body([{"pmcid": "PMC1078728|PMC13900"}])
    assert SERVED in body and "https://www.ncbi.nlm.nih.gov/pmc/articles/13900" in body, body


def test_negated_pmcid():
    body = _body([{"pmcid": "!PMC1078728"}])
    assert SERVED in body and "must_not" in body, body


# oxjob #2155: a work holding several PubMed records serves one PMID / PMCID; the others are its PubMed / PMC copies'
# landing pages, and pmid: / pmcid: find the work by them too (as doi: matches any location's DOI, #1573).
PUBMED = "https://pubmed.ncbi.nlm.nih.gov/35202565"


def _clauses(filters):
    return filter_records(works_fields_dict, filters, Search()).to_dict()


@pytest.mark.parametrize("param", ["pmid", "ids.pmid"])
@pytest.mark.parametrize("value", ["35202565", PUBMED])
def test_pmid_matches_served_or_held_copy(param, value):
    body = json.dumps(_clauses([{param: value}]))
    assert '"ids.pmid": "%s"' % PUBMED in body, body
    assert '"locations_full.landing_page_url": ["%s"]' % PUBMED in body, body


def test_pmcid_matches_both_pmc_copy_url_forms():
    body = json.dumps(_clauses([{"pmcid": "PMC1078728"}]))
    assert '"locations_full.landing_page_url": ["%s", "%s"]' % (SERVED, HELD_PMC) in body, body


def test_or_of_pmids_matches_held_copies():
    body = json.dumps(_clauses([{"pmid": "35202565|34580676"}]))
    assert '"terms": {"ids.pmid": ["%s", "https://pubmed.ncbi.nlm.nih.gov/34580676"]}' % PUBMED in body, body
    assert '"terms": {"locations_full.landing_page_url": ["%s", "https://pubmed.ncbi.nlm.nih.gov/34580676"]}' % PUBMED in body, body


def test_negated_pmid_excludes_served_and_held():
    # was a must_not term on the bare digits, which ids.pmid never stores, so it excluded nothing
    body = json.dumps(_clauses([{"pmid": "!35202565"}]))
    assert "must_not" in body and '"ids.pmid": "%s"' % PUBMED in body and "locations_full.landing_page_url" in body, body
    assert '"ids.pmid": "35202565"' not in body, body
