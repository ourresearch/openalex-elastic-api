"""Awards, funders and sources output fixes from Casey's API review (12 Nov 2026): DOIs in works' https://doi.org/ form, funders'
works_api_url / awards_api_url, and summary_stats.2yr_mean_citedness to 2 decimals on funders and sources.

All three are done where the API writes its answer: the indexes keep what they hold (bare DOIs, full-length means), so
nothing is re-sent, and the filters still read the stored values. No ES needed: these assert on the schemas' output and on
the queries the fields build.
"""
import copy
import json

import pytest
from elasticsearch_dsl import AttrDict

from authors.schemas import AuthorsSchema
from awards.fields import fields_dict as awards_fields
from awards.schemas import AwardsSchema
from funders.fields import fields_dict as funders_fields
from funders.schemas import FundersSchema
from institutions.schemas import InstitutionsSchema
from sources.fields import fields_dict as sources_fields
from sources.schemas import SourcesSchema
from works.fields import fields_dict as works_fields
from works.schemas import WorksSchema

NIH = "https://openalex.org/F4320332161"
NIH_DOI = "10.13039/100000002"


@pytest.fixture(autouse=True)
def no_merges(monkeypatch):
    monkeypatch.setattr("core.merged_ids.merged_winners", lambda short_ids, connection="default": {})


def _hit(**source):
    return AttrDict({"meta": {"score": None}, **source})


def _query(fields, param, value):
    f = copy.deepcopy(fields[param])
    f.value = value
    return f.build_query().to_dict()


# 1. DOIs

@pytest.mark.parametrize("stored, served", [
    ("10.3030/777483", "https://doi.org/10.3030/777483"),                      # G2269547442
    ("http://dx.doi.org/10.3030/777483", "https://doi.org/10.3030/777483"),    # G4904808352: an older URL form
    ("https://doi.org/10.46936/Ab.CD", "https://doi.org/10.46936/ab.cd"),      # lower case, as works' DOIs
    ("not a doi", "not a doi"),                                                # served as stored
    (None, None),
])
def test_award_doi_is_served_as_works_serve_theirs(stored, served):
    assert AwardsSchema(only=("doi",)).dump({"doi": stored}) == {"doi": served}


def test_funder_doi_is_served_as_a_url_on_awards_and_on_funders():
    award = AwardsSchema(only=("funder",)).dump({"funder": {"id": "https://openalex.org/F4320320300", "doi": "10.13039/501100000780"}})
    assert award["funder"]["doi"] == "https://doi.org/10.13039/501100000780"
    funder = FundersSchema(only=("ids",)).dump(_hit(id=NIH, ids={"openalex": NIH, "crossref": "100000002", "doi": NIH_DOI}))
    assert funder["ids"]["doi"] == f"https://doi.org/{NIH_DOI}"
    assert funder["ids"]["crossref"] == "100000002"
    assert "doi" not in FundersSchema(only=("ids",)).dump(_hit(id=NIH, ids={"openalex": NIH}))["ids"]   # no DOI: no key, as before


@pytest.mark.parametrize("fields, param, es_field", [
    (awards_fields, "funder.doi", "funder.doi"),
    (funders_fields, "ids.doi", "ids.doi.keyword"),
])
def test_the_doi_filters_take_the_served_url_and_the_bare_doi(fields, param, es_field):
    """The index holds the bare DOI; the served URL used to match nothing (0 awards, 0 funders on 12 Nov)."""
    bare = _query(fields, param, NIH_DOI)
    terms = {(list(c["term"])[0], c["term"][es_field]["value"]) for c in bare["bool"]["should"]}
    assert (es_field, NIH_DOI) in terms
    for form in (f"https://doi.org/{NIH_DOI}", f"http://dx.doi.org/{NIH_DOI}", f"doi:{NIH_DOI}", NIH_DOI.upper()):
        assert _query(fields, param, form) == bare, form
    assert _query(fields, param, f"!https://doi.org/{NIH_DOI}") == {"bool": {"must_not": bare["bool"]["should"]}}
    assert _query(fields, param, "!null") == {"exists": {"field": es_field}}
    f = copy.deepcopy(fields[param])
    either = f.build_terms_query([f"https://doi.org/{NIH_DOI}", "10.13039/501100000780"]).to_dict()
    assert json.dumps(either).count("10.13039/501100000780") == 3 and json.dumps(either).count(NIH_DOI) == 3


# 2. Funders' link-outs

def test_a_funder_links_to_its_works_and_its_awards():
    out = FundersSchema().dump(_hit(id=NIH, works_count=1964122, awards_count=447656, updated_date="2026-11-12T04:04:43"))
    assert out["works_api_url"] == "https://api.openalex.org/works?filter=funders.id:F4320332161"
    assert out["awards_api_url"] == "https://api.openalex.org/awards?filter=funder.id:F4320332161"
    names = list(out)
    assert names.index("awards_api_url") == names.index("works_api_url") + 1 == names.index("updated_date") - 1
    only = FundersSchema(only=("awards_api_url",)).dump(_hit(id=NIH))            # select=awards_api_url alone
    assert only == {"awards_api_url": out["awards_api_url"]}


def test_the_links_name_filters_that_find_the_funder():
    out = FundersSchema().dump(_hit(id=NIH))
    for url, fields in ((out["works_api_url"], works_fields), (out["awards_api_url"], awards_fields)):
        key, value = url.split("filter=", 1)[1].split(":", 1)
        assert NIH in json.dumps(_query(fields, key, value)), url


# 3. Decimals: summary_stats.2yr_mean_citedness on funders and sources, and nothing else

@pytest.mark.parametrize("schema, stored, served", [
    (FundersSchema, 7.806637963309622, 7.81),          # F4320332161
    (FundersSchema, 8.160333333333334, 8.16),          # F4320321921: "33 repeating"
    (SourcesSchema, 6.798047238270649e-08, 0.0),       # S7407052672: "e minus 8"
    (SourcesSchema, 0.7845640048259341, 0.78),         # S4306525036
    (SourcesSchema, 0, 0.0),
])
def test_mean_citedness_takes_2_decimals_on_funders_and_sources(schema, stored, served):
    stats = {"2yr_mean_citedness": stored, "h_index": 2132, "i10_index": 1381814}
    out = schema(only=("summary_stats",)).dump(_hit(id="https://openalex.org/X1", summary_stats=stats))
    assert out["summary_stats"] == {**stats, "2yr_mean_citedness": served}
    assert "e-" not in json.dumps(out)
    assert schema(only=("summary_stats",)).dump(_hit(id="https://openalex.org/X1"))["summary_stats"] is None


def test_the_filter_still_reads_the_stored_mean():
    for fields in (funders_fields, sources_fields):
        assert _query(fields, "summary_stats.2yr_mean_citedness", ">7.8") == {"range": {"summary_stats.2yr_mean_citedness": {"gt": 7.8}}}


def test_no_other_number_is_cut():
    """Rohan 11-12: only what Casey named. Authors' and institutions' means, topic scores and shares, keyword and SDG
    scores, award shares and amounts are served as stored."""
    long = 0.6416000127792358
    stats = {"2yr_mean_citedness": 10.88888888888889, "h_index": 41, "i10_index": 194}
    for schema in (AuthorsSchema, InstitutionsSchema):
        assert schema(only=("summary_stats",)).dump(_hit(id="https://openalex.org/X1", summary_stats=stats))["summary_stats"] == stats
    source = SourcesSchema(only=("topic_share",)).dump(_hit(id="https://openalex.org/S1", topic_share=[{"id": "t", "value": 2.2e-06}]))
    assert source["topic_share"][0]["value"] == 2.2e-06
    award = AwardsSchema(only=("amount", "primary_topic", "keywords", "recipient_countries")).dump({
        "amount": 344774.19999999995, "primary_topic": {"id": "t", "score": 0.333333}, "keywords": [{"id": "k", "score": long}],
        "recipient_countries": [{"country_code": "GB", "share": 0.29031234, "amount_usd": 1044385.07}]})
    assert (award["amount"], award["primary_topic"]["score"], award["keywords"][0]["score"]) == (344774.19999999995, 0.333333, long)
    assert award["recipient_countries"][0]["share"] == 0.29031234
    work = WorksSchema(only=("topics",)).dump(_hit(id="https://openalex.org/W1", topics=[{"id": "t", "score": long}]))
    assert work["topics"][0]["score"] == long
