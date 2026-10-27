"""oxjob #1882: /institution-types, /source-types and /licenses with ?group_by= returned HTTP 500.

Their views add descriptions to dumped["results"], but a group_by response has no "results"
(core.shared_view.format_response), so every group_by raised KeyError since 11 Mar 2026.
No ES: shared_view is stubbed with each response shape.
"""
import pytest

import institution_types.views as it_views
import licenses.views as lic_views
import source_types.views as st_views
from app import create_app

GROUP_BY_RESULT = {
    "meta": {"count": 2, "db_response_time_ms": 1, "page": 1, "per_page": 25, "groups_count": 2},
    "group_by": [{"key": "education", "key_display_name": "education", "doc_count": 5}],
}
LIST_RESULT = {
    "meta": {"count": 1, "db_response_time_ms": 1, "page": 1, "per_page": 25},
    "group_by": [],
    "results": [],
}


@pytest.fixture
def client():
    return create_app("tests.settings").test_client()


@pytest.mark.parametrize(
    "module,path",
    [(it_views, "/institution-types"), (st_views, "/source-types"), (lic_views, "/licenses")],
)
@pytest.mark.parametrize("result", [GROUP_BY_RESULT, LIST_RESULT])
def test_group_by_and_list_both_answer_200(monkeypatch, client, module, path, result):
    monkeypatch.setattr(module, "shared_view", lambda *a, **k: result)
    qs = "?group_by=id" if "results" not in result else ""
    r = client.get(path + qs)
    assert r.status_code == 200, r.data[:300]
    body = r.get_json()
    assert ("results" in body) == ("results" in result)
