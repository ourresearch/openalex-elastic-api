"""Awards `lead_investigator.institutions.id` / `investigators.institutions.id` filters (oxjob #1847 item 9; Rohan 11-10).

Nightly Grants fills each person's institutions[] ({id full URL, display_name, ror, country_code, type, lineage}) as works'
authorships.institutions, and PatchInvestigatorAuthorsMapping maps `lead_investigator.institutions.id` and
`investigators_full.institutions.id` (everyone on the award: lead, co-lead, investigators[]) as keyword. So the filters must take
every value works' `authorships.institutions.id` takes and build the same term on those fields. No ES needed: the merged-id lookup
(core.merged_ids, an ES call) is stubbed to "never merged".
"""
import copy

import pytest

from awards.fields import fields_dict as awards_fields
from works.fields import fields_dict as works_fields

I_FULL = "https://openalex.org/I136199984"
ES = {"lead_investigator.institutions.id": "lead_investigator.institutions.id",
      "investigators.institutions.id": "investigators_full.institutions.id"}


@pytest.fixture(autouse=True)
def no_merges(monkeypatch):
    monkeypatch.setattr("core.merged_ids.merged_winners", lambda short_ids, connection="default": {})


def _query(fields, param, value):
    f = copy.deepcopy(fields[param])
    f.value = value
    return f.build_query().to_dict()


@pytest.mark.parametrize("param", list(ES))
@pytest.mark.parametrize("value", ["I136199984", "i136199984", I_FULL])
def test_institution_id_term_on_the_keyword_path(param, value):
    assert _query(awards_fields, param, value) == {"term": {ES[param]: I_FULL}}


@pytest.mark.parametrize("param", list(ES))
@pytest.mark.parametrize("value", ["I136199984", I_FULL, "!I136199984", "!null", "null"])
def test_same_query_as_works_authorships_institutions_id_on_the_award_field(param, value):
    works = str(_query(works_fields, "authorships.institutions.id", value)).replace("authorships_full.institutions.id", ES[param])
    assert str(_query(awards_fields, param, value)) == works, (param, value)


def _filtered(fields, param, value):
    from elasticsearch_dsl import Search
    from core.filter import filter_records
    return filter_records(copy.deepcopy(fields), [{param: value}], Search()).to_dict()["query"]


@pytest.mark.parametrize("param", list(ES))
@pytest.mark.parametrize("value", ["I136199984|I27837315", "!I136199984|I27837315", "I136199984 I27837315"])
def test_or_and_negated_or_build_the_works_query_through_the_filter_path(param, value):
    # `|` is split in core.filter, not in build_query: a piped value given to build_query keeps only the first id
    works = str(_filtered(works_fields, "authorships.institutions.id", value)).replace("authorships_full.institutions.id", ES[param])
    assert str(_filtered(awards_fields, param, value)) == works, (param, value)
    if value == "I136199984|I27837315":
        assert _filtered(awards_fields, param, value) == \
            {"bool": {"filter": [{"terms": {ES[param]: [I_FULL, "https://openalex.org/I27837315"]}}]}}


def test_not_null_and_negation():
    assert _query(awards_fields, "investigators.institutions.id", "!null") == {"exists": {"field": "investigators_full.institutions.id"}}
    assert _query(awards_fields, "lead_investigator.institutions.id", "!I136199984") == \
        {"bool": {"must_not": [{"term": {"lead_investigator.institutions.id": I_FULL}}]}}


def test_advanced_search_looks_values_up_as_institutions():
    assert awards_fields["lead_investigator.institutions.id"].entity_type == "institutions"
    assert awards_fields["investigators.institutions.id"].entity_type == "institutions"
