"""study-designs entity wiring (oxjob #1312). Uses the tests/conftest `client`
fixture; ES is never reached (the index study-designs-v1 is built by walden).

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_study_designs_entity.py -q
"""

import ids.views


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


def test_single_record_lookup_uses_the_study_designs_path_segment(client, monkeypatch):
    # index.split("-")[0] would give "study"; the branch in ids/views keeps "study-designs"
    _FakeSearch.calls = []
    monkeypatch.setattr(ids.views, "Search", _FakeSearch)
    r = client.get("/study-designs/Meta-Analysis")
    assert r.status_code == 404  # fake ES has no docs
    assert b"No study-designs found" in r.data
    index, queries = _FakeSearch.calls[-1]
    assert index == "study-designs-v1"
    assert queries == [{"term": {"id.lower": "https://openalex.org/study-designs/meta-analysis"}}]


def test_config_route_serves_the_seven_values(client):
    r = client.get("/study-designs/config")
    assert r.status_code == 200
    ids_ = [v["id"] for v in r.get_json()["values"]]
    assert ids_ == [
        "study-designs/randomized-controlled-trial",
        "study-designs/clinical-trial",
        "study-designs/observational-study",
        "study-designs/case-report",
        "study-designs/systematic-review",
        "study-designs/meta-analysis",
        "study-designs/study-protocol",
    ]


def test_properties_catalog(client):
    props = client.get("/properties").get_json()["properties"]
    assert "study-designs" in props
    works_prop = props["works"]["study_designs.id"]
    assert works_prop["entity_type"] == "study-designs"
    assert works_prop["display_name"] == "study design"
    assert works_prop["category"] == "aboutness"
