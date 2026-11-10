"""Awards `lead_investigator.author.id` / `investigators.author.id` filters (oxjob #1847, grants on author profiles).

awards-v4 maps `lead_investigator.author.id` and `investigators_full.author.id` as keyword and the nightly stores the full
form (https://openalex.org/A…), so the short and full forms must build the same term. No ES needed: these assert on the
queries the fields build; the merged-id lookup (core.merged_ids, an ES call) is stubbed to "never merged".
"""
import copy

import pytest

from awards.fields import fields_dict as awards_fields

A_FULL = "https://openalex.org/A5074402502"


@pytest.fixture(autouse=True)
def no_merges(monkeypatch):
    monkeypatch.setattr("core.merged_ids.merged_winners", lambda short_ids, connection="default": {})


def _field(param, value):
    f = copy.deepcopy(awards_fields[param])
    f.value = value
    return f


@pytest.mark.parametrize("param, es_field", [("lead_investigator.author.id", "lead_investigator.author.id"),
                                             ("investigators.author.id", "investigators_full.author.id")])
@pytest.mark.parametrize("value", ["A5074402502", "a5074402502", A_FULL])
def test_author_id_term(param, es_field, value):
    q = _field(param, value).build_query().to_dict()
    assert q == {"term": {es_field: A_FULL}}, q


def test_author_id_negated_and_null():
    assert _field("investigators.author.id", "!A5074402502").build_query().to_dict() == \
        {"bool": {"must_not": [{"term": {"investigators_full.author.id": A_FULL}}]}}
    assert _field("investigators.author.id", "!null").build_query().to_dict() == {"exists": {"field": "investigators_full.author.id"}}


def test_an_investigators_author_has_works_author_fields_with_a_null_orcid_when_there_is_none():
    """Rohan + Casey 11-09: {id, display_name, orcid} as works' authorships[].author; orcid null, not absent, when the profile has
    none (the Nightly's to_json drops NULLs). The person's printed orcid is untouched."""
    from awards.schemas import InvestigatorSchema
    author = {"id": "https://openalex.org/A5023888391", "display_name": "Jason Priem", "orcid": "https://orcid.org/0000-0001-6187-6610"}
    person = InvestigatorSchema().dump({"given_name": "Jason", "family_name": "Priem", "orcid": "0000-0001-6187-6610", "author": author})
    assert person["author"] == author and person["orcid"] == "0000-0001-6187-6610"
    bare = InvestigatorSchema().dump({"given_name": "Ana", "family_name": "Silva", "author": {"id": "https://openalex.org/A1", "display_name": "Ana Silva"}})
    assert bare["author"] == {"id": "https://openalex.org/A1", "display_name": "Ana Silva", "orcid": None}
    assert InvestigatorSchema().dump({"given_name": "Ana", "family_name": "Silva", "author": None})["author"] is None


def test_an_investigators_institutions_have_institution_awardeds_shape_and_are_empty_until_filled():
    from awards.schemas import InstitutionAwardedSchema, InvestigatorSchema
    inst = {"id": "https://openalex.org/I136199984", "display_name": "Harvard University", "country_code": "US", "lineage": []}
    person = InvestigatorSchema().dump({"given_name": "Ana", "family_name": "Silva", "affiliation": {"name": "Harvard"}, "institutions": [inst]})
    assert person["institutions"] == InstitutionAwardedSchema(many=True).dump([inst])
    assert person["institutions"][0]["ror"] is None and person["institutions"][0]["type"] is None      # null, not absent
    assert person["affiliation"]["name"] == "Harvard"                        # the raw value stays as it is
    assert InvestigatorSchema().dump({"given_name": "Ana", "family_name": "Silva"})["institutions"] == []
