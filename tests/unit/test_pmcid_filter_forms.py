"""oxjob #1862: works serve ids.pmcid in the legacy digits form (https://www.ncbi.nlm.nih.gov/pmc/articles/1078728),
which /works/pmcid: already builds. The pmcid / ids.pmcid filters must reach that form from every way users write a
PMCID: PMC1078728, 1078728, a version suffix, and either NCBI URL. Query-DSL only (no ES, no app): run with --noconftest."""
import json

import pytest
from elasticsearch_dsl import Search

from core.filter import filter_records
from works.fields import fields_dict as works_fields_dict

SERVED = "https://www.ncbi.nlm.nih.gov/pmc/articles/1078728"


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
    # the PMC-prefixed form is never stored on ids.pmcid, and held PMC copies are not matched (oxjob #2155)
    assert body.count("PMC1078728") == 0 and "landing_page_url" not in body, body


def test_or_of_pmcids():
    body = _body([{"pmcid": "PMC1078728|PMC13900"}])
    assert SERVED in body and "https://www.ncbi.nlm.nih.gov/pmc/articles/13900" in body, body


def test_negated_pmcid():
    body = _body([{"pmcid": "!PMC1078728"}])
    assert SERVED in body and "must_not" in body, body


# oxjob #2155: pmid: / pmcid: match the served id only. A PubMed / PMC copy a work merely holds is another article
# about 1 time in 5 (PMIDs) and 1 in 15 (PMC) per NCBI (11 Nov), so held copies are never matched (they were from 07:05 CT 11 Nov until this commit).
PUBMED = "https://pubmed.ncbi.nlm.nih.gov/35202565"


def _clauses(filters):
    return filter_records(works_fields_dict, filters, Search()).to_dict()


@pytest.mark.parametrize("param", ["pmid", "ids.pmid"])
@pytest.mark.parametrize("value", ["35202565", PUBMED])
def test_pmid_matches_the_served_id_only(param, value):
    body = json.dumps(_clauses([{param: value}]))
    assert '"ids.pmid": "%s"' % PUBMED in body, body
    assert "landing_page_url" not in body, body


def test_pmcid_matches_the_served_id_only():
    body = json.dumps(_clauses([{"pmcid": "PMC1078728"}]))
    assert SERVED in body and "landing_page_url" not in body, body


def test_or_of_pmids_matches_served_ids_only():
    body = json.dumps(_clauses([{"pmid": "35202565|34580676"}]))
    assert '"terms": {"ids.pmid": ["%s", "https://pubmed.ncbi.nlm.nih.gov/34580676"]}' % PUBMED in body, body
    assert "landing_page_url" not in body, body


def test_negated_pmid_excludes_the_served_url_form():
    # was a must_not term on the bare digits, which ids.pmid never stores, so it excluded nothing
    body = json.dumps(_clauses([{"pmid": "!35202565"}]))
    assert "must_not" in body and '"ids.pmid": "%s"' % PUBMED in body, body
    assert '"ids.pmid": "35202565"' not in body and "landing_page_url" not in body, body
