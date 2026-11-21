"""What kind of agent an author is (oxjob #2437). No ES, no app.

Authors carry `type` and each works authorship's `author` carries `type`: human, organization or
software-agent, null when not stated (most authors). Works filter on any authorship
(`authorships.author.type`); its negation keeps the works where NO authorship matches, so
`!software-agent` keeps untyped authors and works with no authors. Authors filter on bare `type`.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_author_type.py --noconftest -q
"""
import logging

import pytest
from elasticsearch_dsl import AttrDict, Search

from authors.fields import fields_dict as authors_fields
from core.filter import filter_records
from core.group_by.display_names import get_key_display_name
from core.validate import group_by_rejection
from works.fields import fields_dict as works_fields

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given

ES = "authorships_full.author.type.lower"
FORMS = ["software-agent", "author-types/software-agent", "https://openalex.org/author-types/software-agent"]


def _q(fields_dict, key, value):
    """The one filter clause `filter=<key>:<value>` adds."""
    (clause,) = filter_records(fields_dict, [{key: value}], Search()).to_dict()["query"]["bool"]["filter"]
    return clause


@pytest.mark.parametrize("value", FORMS)
def test_works_filter_takes_the_slug_the_short_id_and_the_full_id(value):
    assert _q(works_fields, "authorships.author.type", value) == {"term": {ES: "software-agent"}}


@pytest.mark.parametrize("value", FORMS)
def test_works_negation_means_no_authorship_is_that_type(value):
    # a must_not over the (non-nested) authorships array: a work is kept only when no authorship
    # holds the value, so untyped authors and works with no authorships are kept
    assert _q(works_fields, "authorships.author.type", "!" + value) == {
        "bool": {"must_not": [{"term": {ES: "software-agent"}}]}}


def test_works_or_list_null_and_entity_type():
    assert _q(works_fields, "authorships.author.type", "software-agent|author-types/organization") == {
        "terms": {ES: ["software-agent", "organization"]}}
    assert _q(works_fields, "authorships.author.type", "null") == {
        "bool": {"must_not": [{"exists": {"field": ES}}]}}
    f = works_fields["authorships.author.type"]
    assert f.entity_type == "author-types"
    assert group_by_rejection(f) is None


@pytest.mark.parametrize("value", ["human", "author-types/human", "https://openalex.org/author-types/human"])
def test_authors_type_filter(value):
    assert _q(authors_fields, "type", value) == {"term": {"type.lower": "human"}}
    assert _q(authors_fields, "type", "!" + value) == {"bool": {"must_not": [{"term": {"type.lower": "human"}}]}}
    assert authors_fields["type"].entity_type == "author-types"


@pytest.mark.parametrize("key,name", [("human", "Human"), ("organization", "Organization"),
                                      ("software-agent", "Software agent"), ("other", "other")])
def test_group_by_rows_are_named_from_the_vocabulary(key, name):
    assert get_key_display_name(AttrDict({"key": key}), "authorships.author.type") == name


def test_relationship_rows_still_named():
    assert get_key_display_name(AttrDict({"key": "data-series"}), "parent_works.relationship") == "Data series"


def test_authorship_author_dumps_type_after_display_name():
    from works.schemas import WorksSchema

    author = {"id": "https://openalex.org/A5000000001", "display_name": "An agent", "type": "software-agent",
              "orcid": None}
    out = WorksSchema(only=("authorships",)).dump({"authorships": [{"author": author}]})
    dumped = out["authorships"][0]["author"]
    assert dumped["type"] == "software-agent"
    assert list(dumped)[:3] == ["id", "display_name", "type"]


def test_authorship_author_without_type_dumps_null():
    # not stated, or before the works re-sync brings the field to the doc
    from works.schemas import WorksSchema

    out = WorksSchema(only=("authorships",)).dump({"authorships": [{"author": {"id": "x", "display_name": "A"}}]})
    assert "type" in out["authorships"][0]["author"]
    assert out["authorships"][0]["author"]["type"] is None


def test_single_work_reads_type_from_authorships_full():
    from works.schemas import WorksSchema

    doc = AttrDict({
        "authorships": [{"author": {"id": "x", "display_name": "A"}}],
        "authorships_full": [{"author": {"id": "x", "display_name": "A", "type": "software-agent"}}],
    })
    schema = WorksSchema(only=("authorships",), context={"single_record": True})
    assert schema.dump(doc)["authorships"][0]["author"]["type"] == "software-agent"


@pytest.mark.parametrize("doc,expected", [({"display_name": "A"}, None),
                                          ({"display_name": "A", "type": "organization"}, "organization")])
def test_authors_record_dumps_type_after_display_name(doc, expected):
    from authors.schemas import AuthorsSchema

    out = AuthorsSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert out["type"] == expected
    keys = list(out)
    assert keys[keys.index("display_name") + 1] == "type"


# --- acted_on_behalf_of (oxjob #2437): plumbed, always [] until a source states a delegation ---------
@pytest.mark.parametrize("authorship", [{"author": {"id": "x"}}, {"acted_on_behalf_of": None}])
def test_acted_on_behalf_of_dumps_an_empty_list(authorship):
    from works.schemas import WorksSchema

    out = WorksSchema(only=("authorships",)).dump({"authorships": [authorship]})
    assert out["authorships"][0]["acted_on_behalf_of"] == []


def test_acted_on_behalf_of_follows_author():
    from works.schemas import WorksSchema

    rows = [{"id": "https://openalex.org/I27837315", "display_name": "A university"}]
    out = WorksSchema(only=("authorships",)).dump(
        {"authorships": [{"author": {"id": "x"}, "acted_on_behalf_of": rows, "is_corresponding": True}]})
    authorship = out["authorships"][0]
    keys = list(authorship)
    assert keys[keys.index("author") + 1] == "acted_on_behalf_of"
    assert authorship["acted_on_behalf_of"] == rows
    assert list(authorship["acted_on_behalf_of"][0]) == ["id", "display_name"]
