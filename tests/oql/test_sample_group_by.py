"""A sample with a group by is refused on every door (oxjob #2033). No ES: the refusal answers before a search runs.

A sample is a random order with the count cut to N; a group by always counts every match. The OQL door used to answer
count N beside groups adding up to the whole set, while the URL door refused the same query.
"""
import flask
import pytest

from core.exceptions import APIQueryParamsError
from core.params import parse_params
from core.validate import validate_sample_view

app = flask.Flask(__name__)
REFUSAL = "sample doesn't work with group_by"


def _parse(url):
    with app.test_request_context(url):
        return parse_params(flask.request)


def _message(body):
    return body.get_json()["validation"]["errors"][0]["message"]


@pytest.mark.parametrize("url", [
    "/works?filter=publication_year:2020&group_by=type&sample=1000",
    "/works?group-by=type&sample=10&seed=1",
    "/works?group_bys=type,publication_year&sample=10",
    "/works?group_bys=cited_by_count_sum&sample=10",   # a sum of every match, beside a count of 10
    "/works?cited_by_count_sum=true&sample=10",
    "/authors?group_by=last_known_institutions.country_code&sample=50",
    "/works?group_by=type&sample=100&page=2",          # told about the group by, not to add a seed first
    "/works?group_by=type&sample=1000&cursor=*",       # told about the group by, not to page with a seed
])
def test_url_door_refuses_sample_with_a_group_by(url):
    with pytest.raises(APIQueryParamsError, match=REFUSAL):
        _parse(url)


@pytest.mark.parametrize("url", [
    "/works?filter=publication_year:2020&group_by=type",
    "/works?filter=publication_year:2020&sample=1000&seed=1&per_page=200&page=2",
    "/works?sample=0&group_by=type",  # sample=0 is no sample
])
def test_group_by_alone_and_sample_alone_still_work(url):
    _parse(url)


def test_the_refusal_says_what_to_do():
    with pytest.raises(APIQueryParamsError) as e:
        validate_sample_view({"sample": 1000, "group_by": "type", "per_page": 25})
    message = str(e.value)
    assert "not the 1000 sampled results" in message
    assert "Drop sample" in message and "drop group_by" in message


def _oql(oql, view_params=None):
    from query_translation.execution import execute_oql_string
    with app.test_request_context("/", method="POST"):
        body, status = execute_oql_string(oql, view_params=view_params or {})
    return status, _message(body)


@pytest.mark.parametrize("oql,view_params", [
    ("get works where year is 2020; then, sample 1000 of those works; finally, group those works by type", {}),
    ("get works where year is 2020; then, sample 50 of those works with seed 42; finally, group those works by year",
     {}),
    ("get works where year is 2020; then, sample 1000 of those works; finally, group those works by type",
     {"cursor": "*", "per_page": 200}),
])
def test_oql_door_refuses_sample_with_a_group_by(oql, view_params):
    status, message = _oql(oql, view_params)
    assert status == 400 and REFUSAL in message


def test_a_walk_refuses_a_sample_before_it_runs(monkeypatch):
    # a walk answers on its own: it used to count the authors of every match, the sample dropped without a word
    from query_translation import execution
    monkeypatch.setattr(execution, "_run_walks", lambda *a, **k: pytest.fail("ran a walk on a refused query"))
    status, message = _oql("get works where title-abstract-keywords has (kelp); then, sample 100 of those works; "
                           "then, get authors of those works; finally, summarize all those authors using count")
    assert status == 400 and "don't combine with sample" in message


def test_a_sampled_list_of_a_set_in_parentheses_still_runs(monkeypatch):
    # a set in parentheses resolves to ids and leaves a list a list (oxjob #1930): its sample is honoured
    from query_translation import execution
    monkeypatch.setattr(execution, "_run_walks", lambda *a, **k: (flask.jsonify({"reached": True}), 200))
    with app.test_request_context("/", method="POST"):
        body, status = execution.execute_oql_string(
            "get works where it cites works in (get works where published in (2020)); "
            "then, sample 10 of those works with seed 1", view_params={})
    assert status == 200 and body.get_json() == {"reached": True}


def test_oqo_door_refuses_sample_with_a_group_by():
    from query_translation.execution import execute_oqo_dict
    oqo = {"get_rows": "works", "filter_rows": [{"column_id": "publication_year", "value": 2020}],
           "sample": 100, "group_by": [{"column_id": "type"}]}
    with app.test_request_context("/", method="POST"):
        body, status = execute_oqo_dict(oqo, view_params={"per_page": 200})
    assert status == 400 and REFUSAL in _message(body)
