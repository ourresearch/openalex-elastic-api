"""The API says what it did (oxjob #2003). No ES: every check here answers before a search runs.

- Semantic search refuses sort, sample and rerank instead of dropping them.
- A sample bigger than one page refuses a cursor, whose walk stopped after page 1 (both doors).
- A page that asked for rerank and came back in the normal order says why (meta.rerank_reason), including when the
  proxy shed rerank while search was under heavy load (X-Rerank-Shed header).
"""
import flask
import pytest

from core import rerank, vector_index
from core.exceptions import APIQueryParamsError
from core.params import parse_params
from core.schemas import MetaSchema
from core.validate import validate_sample_cursor, validate_semantic_view

app = flask.Flask(__name__)


def _parse(url):
    with app.test_request_context(url):
        return parse_params(flask.request)


# ---------- semantic search ----------

@pytest.mark.parametrize("params", [
    {"sort": {"publication_year": "desc"}},
    {"sort": {"cited_by_count": "desc"}},
    {"sort": {"relevance_score": "asc"}},
    {"sort": {"relevance_score": "desc", "publication_year": "desc"}},
    {"sample": 5},
])
def test_semantic_refuses_sort_and_sample(params):
    with pytest.raises(APIQueryParamsError) as e:
        validate_semantic_view(params)
    assert "search.semantic" in str(e.value)


@pytest.mark.parametrize("params", [{}, {"sort": None}, {"sort": {"relevance_score": "desc"}}, {"sample": None}])
def test_semantic_keeps_its_own_order(params):
    validate_semantic_view(params)


def test_vector_search_refuses_a_sort_before_touching_es(monkeypatch):
    monkeypatch.setattr(vector_index, "embed_query", lambda text: pytest.fail("embedded a refused search"))
    params = _parse("/works?search.semantic=coral%20reef%20bleaching&sort=publication_year:desc")
    with pytest.raises(APIQueryParamsError, match="sort doesn't work with search.semantic"):
        vector_index.vector_semantic_search(params, "works", "walden")


def test_semantic_rerank_is_a_400_on_the_url_door():
    from core.shared_view import shared_view
    with app.test_request_context("/works?search.semantic=coral%20reefs&rerank=true"):
        with pytest.raises(APIQueryParamsError, match="rerank=true can't be combined with search.semantic"):
            shared_view(flask.request, {}, "works-v34", ["-cited_by_count"], connection="walden",
                        extra_valid_params=("rerank",))


# ---------- sample with a cursor ----------

@pytest.mark.parametrize("url", [
    "/works?filter=publication_year:2020&sample=1000&cursor=*&per_page=200",
    "/works?filter=publication_year:2020&sample=1000&seed=1&cursor=*&per_page=200",
    "/works?sample=50&cursor=*",
])
def test_a_sample_bigger_than_a_page_refuses_a_cursor(url):
    with pytest.raises(APIQueryParamsError, match="cursor paging doesn't work with sample"):
        _parse(url)


@pytest.mark.parametrize("url", [
    "/works?sample=200&cursor=*&per_page=200",   # fits on one page: the answer is the whole sample
    "/works?sample=10&cursor=*",
    "/works?sample=1000&seed=1&per_page=200&page=2",
    "/works?cursor=*&per_page=200",
])
def test_samples_that_fit_and_plain_cursors_still_work(url):
    _parse(url)


def test_the_refusal_names_a_paging_recipe():
    with pytest.raises(APIQueryParamsError) as e:
        validate_sample_cursor({"sample": 5000, "cursor": "*", "per_page": 100})
    assert "sample=5000&seed=42&per_page=200&page=1" in str(e.value)


# ---------- why a page wasn't reranked ----------

def _p(**kw):
    p = {"cursor": None, "page": 1, "per_page": 25}
    p.update(kw)
    return p


def test_skip_reasons(monkeypatch):
    monkeypatch.setattr(rerank.settings, "RERANK_ENABLED", True, raising=False)
    monkeypatch.setattr(rerank.settings, "RERANK_WINDOW", 100, raising=False)
    assert rerank.skip_reason(_p()) == "model_unavailable"
    assert rerank.skip_reason(_p(page=4)) == "model_unavailable"   # starts at 75, inside the 100
    assert rerank.skip_reason(_p(page=5)) == "past_window"          # starts at 100
    assert rerank.skip_reason(_p(cursor="*")) == "model_unavailable"
    assert rerank.skip_reason(_p(cursor="IlsxMDBdIg==")) == "past_window"  # a normal cursor: past the window
    assert rerank.skip_reason(_p(cursor=rerank.encode_rerank_cursor(50, rerank.CACHE_PREFIX + "k"))) == "model_unavailable"
    monkeypatch.setattr(rerank.settings, "RERANK_ENABLED", False, raising=False)
    assert rerank.skip_reason(_p()) == "disabled"


def test_shed_note_reads_the_proxy_header():
    with app.test_request_context("/works?search=coral", headers={rerank.SHED_HEADER: "search_busy"}):
        assert rerank.shed_note(flask.request) == {"reranked": False, "rerank_reason": "search_busy"}
    with app.test_request_context("/works?search=coral"):
        assert rerank.shed_note(flask.request) is None


def test_with_shed_note_marks_a_plain_answer():
    from core.shared_view import with_shed_note
    with app.test_request_context("/works?search=coral", headers={rerank.SHED_HEADER: "search_busy"}):
        out = with_shed_note({"meta": {"count": 3}}, flask.request)
    assert out["meta"] == {"count": 3, "reranked": False, "rerank_reason": "search_busy"}


def test_rerank_reason_survives_the_meta_schema():
    dumped = MetaSchema().dump({"count": 1, "reranked": False, "rerank_reason": "past_window"})
    assert dumped["reranked"] is False and dumped["rerank_reason"] == "past_window"
    assert "rerank_reason" not in MetaSchema().dump({"count": 1})


# ---------- the OQL door gets the same answers ----------

SEMANTIC_OQL = 'works where title-abstract is similar to "coral reef bleaching"'


def _oql(oql, view_params, rerank_param=None):
    from query_translation.execution import execute_oql_string
    with app.test_request_context("/", method="POST"):
        if rerank_param is not None:
            flask.g.rerank_param = rerank_param
        body, status = execute_oql_string(oql, view_params=view_params)
        return status, body.get_json()["validation"]["errors"][0]["message"]


def test_oql_sample_bigger_than_a_page_refuses_a_cursor():
    status, message = _oql("works where year is 2020\nsample 1000", {"cursor": "*", "per_page": 200})
    assert status == 400 and "cursor paging doesn't work with sample" in message


def test_oql_semantic_refuses_rerank():
    status, message = _oql(SEMANTIC_OQL, {}, rerank_param=True)
    assert status == 400 and message == rerank.SEMANTIC_REFUSAL


@pytest.mark.parametrize("oql,view_params,expect", [
    (SEMANTIC_OQL, {"sort": "publication_year:desc"}, "sort doesn't work with search.semantic"),
    (SEMANTIC_OQL + "\nsample 5", {}, "sample doesn't work with search.semantic"),
])
def test_oql_semantic_refuses_sort_and_sample(monkeypatch, oql, view_params, expect):
    monkeypatch.setattr(vector_index.settings, "USE_VECTOR_INDEX", True, raising=False)
    monkeypatch.setattr(vector_index, "embed_query", lambda text: pytest.fail("embedded a refused search"))
    status, message = _oql(oql, view_params)
    assert status == 400 and expect in message
