"""Institutions `awards_count` (range filter, sort) and `awards_api_url` (oxjob #1847, grants on institution profiles).

walden's CreateInstitutionsApi counts the awards that name the institution in awards_api.institution_awarded and writes
awards_api_url = /awards?filter=institution_awarded.id:I…, so the count and the link must read the same awards field.
No ES needed: these assert on the queries the fields build and on the schema's output.
"""
import copy

import pytest
from elasticsearch_dsl import AttrDict

from awards.fields import fields_dict as awards_fields
from institutions.fields import fields_dict as institutions_fields
from institutions.schemas import InstitutionsSchema

HARVARD = "https://openalex.org/I136199984"
# The link walden writes for Harvard (CreateInstitutionsApi, awards_api_url).
HARVARD_AWARDS_URL = "https://api.openalex.org/awards?filter=institution_awarded.id:I136199984"


@pytest.fixture(autouse=True)
def no_merges(monkeypatch):
    monkeypatch.setattr("core.merged_ids.merged_winners", lambda short_ids, connection="default": {})


def _field(fields, param, value):
    f = copy.deepcopy(fields[param])
    f.value = value
    return f


@pytest.mark.parametrize("value, bounds", [(">0", {"gt": 0.0}), ("<5", {"lt": 5.0}), ("100-", {"gte": 100.0})])
def test_awards_count_range(value, bounds):
    q = _field(institutions_fields, "awards_count", value).build_query().to_dict()
    assert q == {"range": {"awards_count": bounds}}, q


def test_awards_count_sorts():
    assert institutions_fields["awards_count"].sortable


def test_awards_api_url_names_the_awards_filter_the_count_reads():
    key, value = HARVARD_AWARDS_URL.split("filter=", 1)[1].split(":", 1)
    q = _field(awards_fields, key, value).build_query().to_dict()
    assert q == {"term": {"institution_awarded_full.id": HARVARD}}, q


def _hit(**source):
    return AttrDict({"meta": {"score": None}, "id": HARVARD, **source})


def test_schema_serves_both_fields():
    out = InstitutionsSchema().dump(_hit(awards_count=17885, awards_api_url=HARVARD_AWARDS_URL))
    assert (out["awards_count"], out["awards_api_url"]) == (17885, HARVARD_AWARDS_URL)
    names = list(InstitutionsSchema().fields)
    assert names.index("awards_count") == names.index("works_api_url") + 1   # served beside works_api_url
    assert InstitutionsSchema().dump(_hit())["awards_count"] == 0
