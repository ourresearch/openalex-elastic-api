"""Pull notices on /works (oxjob #2264): a filter or group_by on pull_notice_works.* asks about pulled works, so the
API answers it with a redirect to the same URL plus include_pulled=true, as it does is_pulled. Uses the tests/conftest
`client` fixture; the redirect is answered before ES is reached.

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_pull_notice_works_api.py -q
"""
import pytest


@pytest.mark.parametrize("path", ["/works", "/v2/works"])
@pytest.mark.parametrize("query", ["filter=pull_notice_works.link_type:retraction",
                                   "filter=pull_notice_works.id:W4245876183&per_page=5",
                                   "group_by=pull_notice_works.link_type"])
def test_a_pull_notice_filter_or_group_by_redirects_to_include_pulled(client, path, query):
    r = client.get(f"{path}?{query}")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"{path}?{query}&include_pulled=true")


def test_properties_catalog(client):
    works = client.get("/properties").get_json()["properties"]["works"]
    assert works["pull_notice_works.link_type"]["entity_type"] == "link-types"
    assert works["pull_notice_works.link_type"]["display_name"] == "pull notice link type"
    assert works["pull_notice_works.id"]["display_name"] == "pull notice"
    for key in ("pull_notice_works.link_type", "pull_notice_works.id"):
        assert {"filter", "group_by"} <= set(works[key]["actions"]), key
    assert works["pull_notice_works"]["actions"] == ["column"]
