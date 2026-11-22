"""Pull notices (oxjob #2264). No ES, no app.

A pulled work (retracted, withdrawn or removed) lists the notices that pulled it in `pull_notice_works`
[{id, display_name, link_type}], oldest first, [] when none. The filters `pull_notice_works.id` and
`pull_notice_works.link_type` find works by those notices and, like is_pulled, bring pulled works back: /works
answers them with a redirect to the same URL plus include_pulled=true. The link types retraction, withdrawal and
removal join both vocabularies, and every link type's standard_terms carry `match` (a SKOS mapping level).

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_pull_notice_works.py --noconftest -q
"""
import logging

import pytest
from elasticsearch_dsl import AttrDict, Search
from flask import Flask
from flask import request as flask_request

from core.default_view import PULLED_FIELD_KEYS, hides_pulled, names_pulled, pulled_redirect_location
from core.filter import filter_records
from core.group_by.display_names import get_key_display_name
from core.validate import group_by_rejection
from link_types.schemas import LinkTypesSchema
from query_translation.execution import _hides_pulled
from query_translation.oqo import OQO
from relationships.schemas import RelationshipsSchema
from works.fields import fields_dict
from works.schemas import WorksSchema

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given

W = "https://openalex.org/W2117847125"
NOTICE = "https://openalex.org/W4245876183"
NOTICES = [{"id": NOTICE, "display_name": "Retraction—Ileal-lymphoid-nodular hyperplasia", "link_type": "retraction"},
           {"id": "https://openalex.org/W2", "display_name": "Withdrawal of a duplicate", "link_type": "withdrawal"}]
DOCS = "https://help.openalex.org/data/works/attributes/#pull_notice_works"


def _q(key, value):
    (clause,) = filter_records(fields_dict, [{key: value}], Search()).to_dict()["query"]["bool"]["filter"]
    return clause


def _doc(**fields):
    from works.lakebase import LakebaseHit

    return LakebaseHit(fields)


def _args(query=""):
    with Flask(__name__).test_request_context("/works" + query):
        return flask_request.args.copy()


# --- the record ----------------------------------------------------------------------------------
def test_each_notice_serves_id_display_name_and_link_type_in_stored_order():
    for doc in (_doc(id=W, pull_notice_works=NOTICES), AttrDict({"id": W, "pull_notice_works": NOTICES})):
        out = WorksSchema(only=("id", "pull_notice_works")).dump(doc)
        assert out["pull_notice_works"] == NOTICES
        assert list(out["pull_notice_works"][0]) == ["id", "display_name", "link_type"]


@pytest.mark.parametrize("doc", [{"id": W}, {"id": W, "pull_notice_works": None}, {"id": W, "pull_notice_works": []}])
def test_a_work_with_no_notices_serves_an_empty_list(doc):
    assert WorksSchema(only=("id", "pull_notice_works")).dump(AttrDict(doc)) == {"id": W, "pull_notice_works": []}
    assert WorksSchema(only=("id", "pull_notice_works")).dump(_doc(**doc))["pull_notice_works"] == []


def test_pull_notice_works_sits_after_the_parent_and_child_works():
    keys = list(WorksSchema._declared_fields)
    assert keys[keys.index("child_works_count") + 1] == "pull_notice_works"


# --- the filters ---------------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["retraction", "link-types/retraction", "relationships/retraction",
                                   "https://openalex.org/link-types/retraction",
                                   "https://openalex.org/relationships/retraction"])
def test_link_type_takes_the_key_or_either_id_form(value):
    assert _q("pull_notice_works.link_type", value) == {"term": {"pull_notice_works.link_type.lower": "retraction"}}
    assert _q("pull_notice_works.link_type", "!" + value) == {
        "bool": {"must_not": [{"term": {"pull_notice_works.link_type.lower": "retraction"}}]}}


def test_link_type_or_list_entity_type_and_group_by():
    assert _q("pull_notice_works.link_type", "withdrawal|link-types/removal") == {
        "terms": {"pull_notice_works.link_type.lower": ["withdrawal", "removal"]}}
    field = fields_dict["pull_notice_works.link_type"]
    assert field.entity_type == "link-types"
    assert field.documentation_link == DOCS
    assert group_by_rejection(field) is None


def test_the_id_filter_lists_the_works_one_notice_pulled():
    assert _q("pull_notice_works.id", "W4245876183") == {"term": {"pull_notice_works.id.lower": NOTICE}}
    assert _q("pull_notice_works.id", "!" + NOTICE) == {
        "bool": {"must_not": [{"term": {"pull_notice_works.id.lower": NOTICE}}]}}
    field = fields_dict["pull_notice_works.id"]
    assert field.documentation_link == DOCS
    assert group_by_rejection(field) is None


def test_the_id_filter_takes_work_ids_only():
    with pytest.raises(Exception) as err:
        _q("pull_notice_works.id", "A5023888391")
    assert "pull_notice_works.id takes works IDs" in str(err.value)


@pytest.mark.parametrize("key,name", [("retraction", "Retraction"), ("withdrawal", "Withdrawal"),
                                      ("removal", "Removal"), ("other", "other")])
def test_group_by_rows_are_named_from_the_link_types(key, name):
    assert get_key_display_name(AttrDict({"key": key}), "pull_notice_works.link_type") == name


# --- they bring pulled works back ----------------------------------------------------------------
def test_both_filters_ask_about_pulled_works():
    assert {"pull_notice_works.id", "pull_notice_works.link_type"} <= PULLED_FIELD_KEYS
    assert names_pulled(["pull_notice_works.link_type"]) and names_pulled(["pull-notice-works.id"])
    assert not names_pulled(["pull_notice_works", "pull_notice_works.display_name"])
    assert not hides_pulled(_args(), [{"pull_notice_works.link_type": "retraction"}])
    assert hides_pulled(_args("?include_pulled=false"), [{"pull_notice_works.link_type": "retraction"}])


@pytest.mark.parametrize("query, location", [
    ("filter=pull_notice_works.link_type:retraction",
     "/works?filter=pull_notice_works.link_type:retraction&include_pulled=true"),
    ("filter=type:article,pull_notice_works.id:W4245876183&per_page=5",
     "/works?filter=type:article,pull_notice_works.id:W4245876183&per_page=5&include_pulled=true"),
    ("filter=pull-notice-works.link-type:withdrawal",
     "/works?filter=pull-notice-works.link-type:withdrawal&include_pulled=true"),
    ("group_by=pull_notice_works.link_type", "/works?group_by=pull_notice_works.link_type&include_pulled=true"),
    ("filter=pull_notice_works.link_type:retraction&include_pulled=true", None),
    ("filter=pull_notice_works.link_type:retraction&include_pulled=false", None),
])
def test_redirect_location(query, location):
    assert pulled_redirect_location("/works", query, _args("?" + query)) == location


def test_oqo_naming_a_pull_notice_column_brings_them_back():
    by_kind = OQO.from_dict({"get_rows": "works", "group_by": [{"column_id": "pull_notice_works.link_type"}]})
    one_notice = OQO.from_dict({"get_rows": "works",
                                "filter_rows": [{"column_id": "pull_notice_works.id", "value": "W4245876183"}]})
    with Flask(__name__).test_request_context("/"):
        assert not _hides_pulled(by_kind, "walden")
        assert not _hides_pulled(one_notice, "walden")


# --- the link types ------------------------------------------------------------------------------
def test_both_vocabularies_hold_the_three_pull_notices():
    from core.entities import get_entity_type

    for vocab in ("relationships", "link-types"):
        values = [(v["id"], v["display_name"]) for v in get_entity_type(vocab).values]
        assert values[-3:] == [(f"{vocab}/retraction", "Retraction"), (f"{vocab}/withdrawal", "Withdrawal"),
                               (f"{vocab}/removal", "Removal")]


def test_links_accepts_the_pull_notice_link_types():
    import links.views as lv

    assert lv.relationships("retraction|link-types/removal", "link_type") == ["retraction", "removal"]
    assert "withdrawal" in lv.EXAMPLES


TERMS = [{"vocabulary": "Crossref", "term": "retraction",
          "url": "https://www.crossref.org/documentation/crossmark/participating-in-crossmark/", "match": "exact"},
         {"vocabulary": "MeSH", "term": "Retraction Notice", "url": "http://id.nlm.nih.gov/mesh/D016440",
          "match": "broad"}]


@pytest.mark.parametrize("schema", [LinkTypesSchema, RelationshipsSchema])
def test_standard_terms_carry_match_as_the_index_holds_it(schema):
    doc = {"id": "https://openalex.org/link-types/retraction", "display_name": "Retraction", "standard_terms": TERMS,
           "meta": {"score": None}}
    out = schema(context={"display_relevance": False}).dump(AttrDict(doc))
    assert out["standard_terms"] == TERMS
    assert list(out["standard_terms"][0]) == ["vocabulary", "term", "url", "match"]


@pytest.mark.parametrize("schema", [LinkTypesSchema, RelationshipsSchema])
def test_a_standard_term_written_before_match_serves_null(schema):
    old = [{"vocabulary": "CiTO", "term": "cites", "url": "http://purl.org/spar/cito/cites"}]
    out = schema(context={"display_relevance": False}).dump(AttrDict({"id": "x", "standard_terms": old,
                                                                       "meta": {"score": None}}))
    assert out["standard_terms"] == [{**old[0], "match": None}]
