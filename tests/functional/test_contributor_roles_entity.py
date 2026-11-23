"""contributor-roles entity wiring (oxjob #2075, #2512): the 14 CRediT roles plus editor and translator. Uses the tests/conftest `client`
fixture; ES is never reached (walden builds contributor-roles-v1).

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_contributor_roles_entity.py -q
"""
from elasticsearch_dsl import AttrDict

import ids.views
from contributor_roles.schemas import ContributorRolesSchema

SLUGS = [
    "conceptualization", "data-curation", "formal-analysis", "funding-acquisition", "investigation",
    "methodology", "project-administration", "resources", "software", "supervision", "validation",
    "visualization", "writing-original-draft", "writing-review-editing", "editor", "translator",
]


class _FakeSearch:
    calls = []

    def __init__(self, index=None, using=None):
        self.index = index
        self.queries = []

    def filter(self, q):
        self.queries.append(q.to_dict())
        return self

    def execute(self):
        _FakeSearch.calls.append((self.index, self.queries))
        return []


def test_single_record_lookup_uses_the_contributor_roles_path_segment(client, monkeypatch):
    # index.split("-")[0] would give "contributor"; the branch in ids/views keeps "contributor-roles"
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    r = client.get("/contributor-roles/Software")
    assert r.status_code == 404  # fake ES has no docs
    assert b"No contributor-roles found" in r.data
    index, queries = _FakeSearch.calls[-1]
    assert index == "contributor-roles-v1"
    assert queries == [{"term": {"id.lower": "https://openalex.org/contributor-roles/software"}}]


def test_config_route_serves_the_sixteen_values(client):
    r = client.get("/contributor-roles/config")
    assert r.status_code == 200
    values = r.get_json()["values"]
    assert [v["id"] for v in values] == [f"contributor-roles/{s}" for s in SLUGS]
    assert values[-3]["display_name"] == "Writing – review & editing"
    assert values[-2]["display_name"] == "Editor"
    assert values[-1]["display_name"] == "Translator"


def test_helper_routes(client):
    r = client.get("/contributor-roles/valid_fields")
    assert r.status_code == 200
    assert "works_count" in r.get_json()


def test_the_record_shape():
    doc = {
        "id": "https://openalex.org/contributor-roles/software", "display_name": "Software",
        "description": "Programming, software development; designing computer programs.",
        "standard_terms": [{"vocabulary": "crossref", "term": "software",
                            "url": "http://credit.niso.org/contributor-roles/software/"}],
        "ids": {"openalex": "https://openalex.org/contributor-roles/software",
                "credit": "https://credit.niso.org/contributor-roles/software/"},
        "works_count": 7, "cited_by_count": 9,
        "works_api_url": "https://api.openalex.org/works?filter=authorships.contributor_roles.id:software",  # in ES, not served
        "updated_date": "2026-11-18T00:00:00", "created_date": "2026-11-18",
    }
    out = ContributorRolesSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert list(out) == ["id", "display_name", "description", "standard_terms", "ids", "works_count",
                         "cited_by_count", "updated_date", "created_date"]
    assert out["ids"] == doc["ids"]
    assert out["standard_terms"] == doc["standard_terms"]
    assert list(out["standard_terms"][0]) == ["vocabulary", "term", "url"]


def test_editor_has_no_credit_id():
    # editor is not a CRediT role: ids.credit is null and dumps as null (oxjob #2075)
    doc = {"id": "https://openalex.org/contributor-roles/editor", "display_name": "Editor",
           "ids": {"openalex": "https://openalex.org/contributor-roles/editor", "credit": None},
           "standard_terms": [{"vocabulary": "datacite", "term": "Editor", "url": None}]}
    out = ContributorRolesSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert out["ids"] == {"openalex": "https://openalex.org/contributor-roles/editor", "credit": None}
    assert out["standard_terms"] == doc["standard_terms"]


def test_a_record_before_the_sync_has_no_standard_terms():
    doc = {"id": "https://openalex.org/contributor-roles/software", "display_name": "Software"}
    out = ContributorRolesSchema(context={"display_relevance": False}).dump(AttrDict({**doc, "meta": {"score": None}}))
    assert "standard_terms" not in out


def test_properties_catalog(client):
    props = client.get("/properties").get_json()["properties"]
    assert "contributor-roles" in props
    # no standalone works filter on a role (oxjob #2075, D11): the filter that ships pairs author + role
    assert "authorships.contributor_roles.id" not in props["works"]
