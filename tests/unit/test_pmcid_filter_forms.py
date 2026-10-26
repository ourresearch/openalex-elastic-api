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
    assert "PMC1078728" not in body


def test_or_of_pmcids():
    body = _body([{"pmcid": "PMC1078728|PMC13900"}])
    assert SERVED in body and "https://www.ncbi.nlm.nih.gov/pmc/articles/13900" in body, body


def test_negated_pmcid():
    body = _body([{"pmcid": "!PMC1078728"}])
    assert SERVED in body and "must_not" in body, body
