"""/keywords?search.semantic= via the external keyword-search endpoint (oxjob #1464).

The HTTP call and the ES read are both mocked: these tests check the endpoint contract,
the ES id-fetch shape, ranking order, paging, param rejection, and the fallback to plain
text search when the endpoint is unconfigured or failing. Runs under --noconftest.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests
from elasticsearch_dsl import Search
from flask import Flask

from core import keyword_semantic as ks
from core import shared_view as sv
from core.exceptions import APIQueryParamsError
from keywords.fields import fields_dict
from keywords.schemas import MessageSchema

URL = "https://kw-search.example.modal.run"
TOKEN = "tok-123"
KW = "https://openalex.org/keywords/"


def _endpoint_response(rows):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [
            {"id": KW + kid, "display_name": kid.replace("-", " "), "score": score, "similarity": score}
            for kid, score in rows
        ],
        "model": "m",
        "vocab": "v",
        "ms": 5,
    }
    return response


class _Hit:
    def __init__(self, kid):
        self._doc = {
            "id": KW + kid,
            "display_name": kid.replace("-", " ").title(),
            "works_count": 10,
            "cited_by_count": 3,
        }
        self.meta = MagicMock(id=kid)

    def to_dict(self):
        return dict(self._doc)


def _fake_execute(returned_kids, captured):
    """Search.execute stand-in: records the query body, returns docs in ES (not ranked) order."""

    def execute(self, *args, **kwargs):
        captured.append(self.to_dict())
        return [_Hit(kid) for kid in returned_kids]

    return execute


def _params(**overrides):
    params = {
        "search": "heart attack",
        "search_type": "semantic",
        "search_scope": None,
        "searches": [],
        "filters": None,
        "group_by": None,
        "group_bys": None,
        "cursor": None,
        "page": 1,
        "per_page": 25,
        "sort": None,
        "sample": None,
    }
    params.update(overrides)
    return params


@pytest.fixture
def configured():
    with patch.object(ks.settings, "KEYWORD_SEARCH_URL", URL, create=True), \
            patch.object(ks.settings, "KEYWORD_SEARCH_TOKEN", TOKEN, create=True), \
            patch.object(ks.settings, "KEYWORD_SEARCH_TIMEOUT", 3.0, create=True):
        yield


# --- routing -------------------------------------------------------------------------

def test_only_keywords_semantic_routes():
    assert ks.is_keyword_semantic(_params(), "keywords-v1")
    assert not ks.is_keyword_semantic(_params(), "works-v34")
    assert not ks.is_keyword_semantic(_params(), "topics-v4")
    assert not ks.is_keyword_semantic(_params(search_type="default"), "keywords-v1")
    assert not ks.is_keyword_semantic(_params(search='""'), "keywords-v1")
    assert not ks.is_keyword_semantic(_params(search="   "), "keywords-v1")


def test_unconfigured_by_default():
    with patch.object(ks.settings, "KEYWORD_SEARCH_URL", None, create=True), \
            patch.object(ks.settings, "KEYWORD_SEARCH_TOKEN", None, create=True):
        assert not ks.keyword_search_configured()


# --- endpoint contract ---------------------------------------------------------------

@patch.object(ks.http_requests, "post")
def test_endpoint_call_shape(mock_post, configured):
    mock_post.return_value = _endpoint_response([("myocardial-infarction", 0.9), ("angina", 0.5)])

    ranked = ks.fetch_ranked_keyword_ids("heart attack", 25)

    assert ranked == [(KW + "myocardial-infarction", 0.9), (KW + "angina", 0.5)]
    args, kwargs = mock_post.call_args
    assert args[0] == URL + "/search"
    assert kwargs["headers"] == {"Authorization": "Bearer " + TOKEN}
    assert kwargs["json"] == {"query": "heart attack", "k": 25}
    assert kwargs["timeout"] == 3.0


@patch.object(ks.http_requests, "post")
def test_endpoint_dupes_and_foreign_ids_dropped(mock_post, configured):
    response = _endpoint_response([("a", 0.9), ("a", 0.8), ("b", 0.7)])
    response.json.return_value["results"].append(
        {"id": "https://openalex.org/topics/T1", "score": 0.6, "similarity": 0.6}
    )
    mock_post.return_value = response
    assert ks.fetch_ranked_keyword_ids("q", 10) == [(KW + "a", 0.9), (KW + "b", 0.7)]


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.Timeout("slow"),
        requests.exceptions.ConnectionError("down"),
    ],
)
@patch.object(ks.http_requests, "post")
def test_endpoint_transport_errors_raise_unavailable(mock_post, failure, configured):
    mock_post.side_effect = failure
    with pytest.raises(ks.KeywordSearchUnavailable):
        ks.fetch_ranked_keyword_ids("q", 10)


@patch.object(ks.http_requests, "post")
def test_endpoint_http_error_and_bad_body_raise_unavailable(mock_post, configured):
    bad_status = MagicMock()
    bad_status.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    mock_post.return_value = bad_status
    with pytest.raises(ks.KeywordSearchUnavailable):
        ks.fetch_ranked_keyword_ids("q", 10)

    bad_body = MagicMock()
    bad_body.raise_for_status.return_value = None
    bad_body.json.return_value = {"detail": "nope"}
    mock_post.return_value = bad_body
    with pytest.raises(ks.KeywordSearchUnavailable):
        ks.fetch_ranked_keyword_ids("q", 10)


# --- full keyword path ---------------------------------------------------------------

@patch.object(ks.http_requests, "post")
def test_results_keep_endpoint_order_and_scores(mock_post, configured):
    mock_post.return_value = _endpoint_response(
        [("myocardial-infarction", 0.91), ("angina", 0.62), ("chest-pain", 0.40)]
    )
    captured = []
    # ES returns the docs in a different order; the endpoint's order must win.
    with patch.object(Search, "execute", _fake_execute(["chest-pain", "angina", "myocardial-infarction"], captured)):
        result = ks.keyword_semantic_search(_params(), fields_dict, "keywords-v1", "walden")

    assert [r.id for r in result["results"]] == [
        KW + "myocardial-infarction", KW + "angina", KW + "chest-pain",
    ]
    assert [r.meta.score for r in result["results"]] == [0.91, 0.62, 0.40]
    assert result["meta"]["count"] == 3
    assert result["meta"]["page"] == 1 and result["meta"]["per_page"] == 25

    # READ by id on the keywords index: a terms filter on id.lower, sized to the k ids.
    body = captured[0]
    assert body["size"] == 3
    assert body["query"]["bool"]["filter"] == [
        {"terms": {"id.lower": [KW + "myocardial-infarction", KW + "angina", KW + "chest-pain"]}}
    ]

    # Serializes with relevance_score = endpoint score.
    dumped = MessageSchema().dump(result)
    assert dumped["results"][0]["relevance_score"] == 0.91
    assert dumped["results"][0]["display_name"] == "Myocardial Infarction"


@patch.object(ks.http_requests, "post")
def test_filter_applied_on_id_fetch_and_drops_ranked_ids(mock_post, configured):
    mock_post.return_value = _endpoint_response([("a", 0.9), ("b", 0.8), ("c", 0.7)])
    captured = []
    # "b" fails the filter, so ES doesn't return it.
    with patch.object(Search, "execute", _fake_execute(["c", "a"], captured)):
        result = ks.keyword_semantic_search(
            _params(filters=[{"works_count": ">100"}]), fields_dict, "keywords-v1", "walden"
        )

    assert [r.id for r in result["results"]] == [KW + "a", KW + "c"]
    assert result["meta"]["count"] == 2
    filters = captured[0]["query"]["bool"]["filter"]
    assert {"terms": {"id.lower": [KW + "a", KW + "b", KW + "c"]}} in filters
    assert any("range" in str(f) and "works_count" in str(f) for f in filters)


@patch.object(ks.http_requests, "post")
def test_always_k_200_pages_in_memory_and_counts_all(mock_post, configured):
    rows = [(f"kw-{i}", 1.0 - i / 100) for i in range(20)]
    mock_post.return_value = _endpoint_response(rows)
    with patch.object(Search, "execute", _fake_execute([kid for kid, _ in rows], [])):
        result = ks.keyword_semantic_search(
            _params(page=2, per_page=10), fields_dict, "keywords-v1", "walden"
        )
    assert mock_post.call_args.kwargs["json"]["k"] == 200
    assert [r.id for r in result["results"]] == [KW + f"kw-{i}" for i in range(10, 20)]
    assert result["meta"]["count"] == 20


@patch.object(ks.http_requests, "post")
def test_count_not_capped_by_per_page(mock_post, configured):
    rows = [(f"kw-{i}", 1.0 - i / 100) for i in range(30)]
    mock_post.return_value = _endpoint_response(rows)
    with patch.object(Search, "execute", _fake_execute([kid for kid, _ in rows], [])):
        result = ks.keyword_semantic_search(_params(per_page=5), fields_dict, "keywords-v1", "walden")
    assert len(result["results"]) == 5
    assert result["meta"]["count"] == 30


@patch.object(ks.http_requests, "post")
def test_last_allowed_page_and_empty_list(mock_post, configured):
    mock_post.return_value = _endpoint_response([])
    result = ks.keyword_semantic_search(_params(page=4, per_page=50), fields_dict, "keywords-v1", "walden")
    assert mock_post.call_args.kwargs["json"]["k"] == 200
    assert result["results"] == [] and result["meta"]["count"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"group_by": "works_count"},
        {"cursor": "*"},
        {"per_page": 51},
        {"page": 5, "per_page": 50},
        {"page": 21, "per_page": 10},
        {"filters": [{"display_name.search": "heart"}]},
    ],
)
@patch.object(ks.http_requests, "post")
def test_incompatible_params_rejected_before_endpoint_call(mock_post, overrides, configured):
    with pytest.raises(APIQueryParamsError):
        ks.keyword_semantic_search(_params(**overrides), fields_dict, "keywords-v1", "walden")
    mock_post.assert_not_called()


@patch.object(ks.http_requests, "post")
def test_endpoint_failure_returns_none(mock_post, configured):
    mock_post.side_effect = requests.exceptions.Timeout("slow")
    assert ks.keyword_semantic_search(_params(), fields_dict, "keywords-v1", "walden") is None


# --- shared_view wiring --------------------------------------------------------------

def _run_shared_view(query_string, index_name="keywords-v1"):
    """Run shared_view with the classic text path stubbed, so no ES is touched."""
    app = Flask(__name__)
    sentinel = {"meta": {"count": -1}, "results": [], "group_by": []}
    with app.test_request_context("/keywords?" + query_string) as ctx, \
            patch.object(sv, "construct_query", return_value=MagicMock()) as construct, \
            patch.object(sv, "execute_search", return_value=MagicMock()), \
            patch.object(sv, "format_response", return_value=sentinel), \
            patch.object(sv, "attach_x_query"):
        result = sv.shared_view(ctx.request, fields_dict, index_name, ["-works_count", "id"], connection="walden")
    return result, construct, sentinel


@patch.object(ks.http_requests, "post")
def test_shared_view_uses_endpoint_when_configured(mock_post, configured):
    mock_post.return_value = _endpoint_response([("myocardial-infarction", 0.9)])
    with patch.object(Search, "execute", _fake_execute(["myocardial-infarction"], [])):
        result, construct, sentinel = _run_shared_view("search.semantic=heart+attack")
    assert result is not sentinel
    construct.assert_not_called()
    assert [r.id for r in result["results"]] == [KW + "myocardial-infarction"]


@patch.object(ks.http_requests, "post")
def test_shared_view_falls_back_to_text_search_on_endpoint_error(mock_post, configured):
    mock_post.side_effect = requests.exceptions.ConnectionError("down")
    result, construct, sentinel = _run_shared_view("search.semantic=heart+attack")
    assert result is sentinel
    params = construct.call_args.args[0]
    assert params["search"] == "heart attack"


@patch.object(ks.http_requests, "post")
def test_shared_view_falls_back_when_unconfigured(mock_post):
    with patch.object(ks.settings, "KEYWORD_SEARCH_URL", None, create=True), \
            patch.object(ks.settings, "KEYWORD_SEARCH_TOKEN", None, create=True):
        result, construct, sentinel = _run_shared_view("search.semantic=heart+attack")
    assert result is sentinel
    mock_post.assert_not_called()


@patch.object(ks.http_requests, "post")
def test_shared_view_plain_keyword_search_untouched(mock_post, configured):
    result, _, sentinel = _run_shared_view("search=heart+attack")
    assert result is sentinel
    mock_post.assert_not_called()
