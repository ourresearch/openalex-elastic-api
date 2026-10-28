"""A nested query's summary export pages each split on its own (oxjob #1598, step 6; Jason 2026-10-08: "No
exceptions"): `table=summary&split=<n>` is split n alone over the whole set (its by-<split>.csv, named as in the
summary's zip), and with a cursor it pages like a single split. The one-call summary still lists each split's
biggest groups past the limits; it names those splits in `X-More-Groups-Splits` so the exporter pages them."""
import csv
import io
from collections import Counter
from dataclasses import replace

import pytest
from flask import Flask

from query_translation import analytics as A
from query_translation import analytics_csv, execution
from query_translation.oql_lang import parse
from query_translation.oql_parser import parse_either
from query_translation.oqo_canonicalizer import canonicalize_oqo
from tests.oql.test_nested_pages import OQL, WORKS, FakeES, _setup

COUNT = {"key": "count", "measure": "count", "oql": "count"}
HINDEX = {"key": "summary_stats_h_index", "measure": "value", "oql": "h-index"}   # the engine's key


def _read(text):
    return list(csv.reader(io.StringIO(text)))


def _walk_split(monkeypatch, n, per_page):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    oqo = A.split_alone(parse_either(OQL), n)
    cursor, rows, pages = "*", [], 0
    while cursor and pages < 100:
        body = A.run(replace(oqo, cursor=cursor), index_name="works", connection=None, fields_dict=fields_dict,
                     base_query={"match_all": {}}, per_page=per_page)
        rows += [(r["key"], r["count"]) for r in body["group_by"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
    return rows, pages


def test_split_alone_is_that_split_with_its_own_filter():
    oqo = parse_either("get the count of all works by year and author. Only authors with at least 2 works.")
    alone = A.split_alone(oqo, 2)
    assert alone.group_by == [oqo.group_by[1]] and alone.group_by[0].where is not None
    assert alone.calculate == oqo.calculate and alone.filter_rows == oqo.filter_rows


@pytest.mark.parametrize("per_page", [1, 3, 5, 100])
def test_a_split_on_its_own_walks_every_group_once_in_key_order(monkeypatch, per_page):
    rows, pages = _walk_split(monkeypatch, 1, per_page)
    by_author = Counter(a for au, _ in WORKS for a in set(au))
    assert rows == sorted(by_author.items())
    assert pages >= len(by_author) // per_page


def test_the_inner_split_on_its_own_walks_too(monkeypatch):
    rows, _ = _walk_split(monkeypatch, 2, 2)
    by_year = Counter(y for _, ys in WORKS for y in set(ys))
    assert [(int(k), c) for k, c in rows] == sorted(by_year.items())


def test_past_the_limits_each_summary_split_says_how_many_groups_it_has(monkeypatch):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    body = A.run(parse_either(OQL), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, per_page=3, summary_only=True)
    parts = body["summary"]["splits"]
    assert [p["groups_count"] for p in parts] == [13, 5]   # the probe's distinct authors and years


# --- the CSV -----------------------------------------------------------------------------------------------------

def _oqo(q):
    return canonicalize_oqo(parse(q))


def test_a_split_page_is_its_summary_file_with_fixed_columns():
    oqo = _oqo("get works where year >= (2020); then group those works by author; then group "
               "those works again by year; then summarize using count, h-index")
    splits = [analytics_csv.split_meta(g, "works") for g in oqo.group_by]
    page = {"meta": {"measures": [COUNT, HINDEX], "splits": splits[:1]},
            "group_by": [{"key": "https://openalex.org/A1", "key_display_name": "Ana", "count": 5}]}
    # the author has no h-index on this page, but authors have one: the column stays
    name, text = analytics_csv.split_file(page, oqo, 1)
    assert name == "by-author.csv"
    assert _read(text) == [["author", "author id", "count", "h-index"], ["Ana", "A1", "5", ""]]
    years = {"meta": {"measures": [COUNT, HINDEX]},
             "group_by": [{"key": "2020", "key_display_name": "2020", "count": 10}]}
    name, text = analytics_csv.split_file(years, oqo, 2)
    assert name == "by-year.csv" and _read(text) == [["year", "count"], ["2020", "10"]]


def test_a_split_page_is_named_as_in_the_summary_zip():
    q = ("get works where year >= (2020); then group those works into ((year <= (2021)), "
         "(year >= (2022))); then group those works again into ((type is (article)), "
         "(type is (review))); then summarize using count")
    body = {"meta": {"measures": [COUNT]}, "group_by": [{"key": "c", "key_display_name": "c", "count": 6}]}
    data, name, mime, rows = analytics_csv.build_download(body, _oqo(q), q, "summary", split=2)
    assert mime == "text/csv" and rows == 1 and name.endswith("-summary-by-condition-2.csv")
    assert _read(data.decode()) == [["condition", "count"], ["c", "6"]]


# --- the request -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("args,ok", [
    ("format=csv&table=summary&split=1", True),
    ("format=csv&table=summary&split=2", True),
    ("format=csv&table=summary&split=3", False),     # two splits
    ("format=csv&table=summary&split=0", False),
    ("format=csv&table=summary&split=x", False),
    ("format=csv&table=groups&split=1", False),      # a table of the summary
    ("table=summary&split=1", False),                # a download
])
def test_split_names_one_split_of_the_summary(args, ok):
    with Flask(__name__).test_request_context("/?" + args):
        refused = execution._split_refusal(parse_either(OQL), execution._split_asked(), "format=csv" in args)
    assert (refused is None) == ok
    if not ok:
        assert refused[1] == 400 and refused[0].get_json()["error"] == "invalid_split"


def test_one_split_has_no_split_to_pick():
    with Flask(__name__).test_request_context("/?format=csv&table=summary&split=1"):
        refused = execution._split_refusal(parse_either("get the count of all works by year"), "1", True)
    assert refused[0].get_json()["error"] == "invalid_split"


def _summary_body(oqo, more):
    splits = [analytics_csv.split_meta(g, oqo.get_rows) for g in oqo.group_by]
    row = {"key": "https://openalex.org/A0001", "key_display_name": "A1", "count": 3}
    year = {"key": "2020", "key_display_name": "2020", "count": 7}
    return {"meta": {"measures": [COUNT], "splits": splits},
            "summary": {"all": {"key": "all", "count": 16},
                        "splits": [{"groups": [row], "more_groups": more[0], "groups_count": 13},
                                   {"groups": [year], "more_groups": more[1], "groups_count": None}]},
            "group_by": []}


def test_the_summary_names_the_splits_it_cut_for_the_exporter():
    oqo = parse_either(OQL)
    with Flask(__name__).test_request_context("/?format=csv&table=summary"):
        resp, status = execution._csv_response(oqo, _summary_body(oqo, (True, False)), A.price(oqo))
    assert status == 200
    # n:<file>:<its groups> (empty when not known: a count floor)
    assert resp.headers["X-More-Groups-Splits"] == "1:by-author.csv:13"
    assert "split=1&cursor=*" in resp.headers["X-Groups-Note"]
    with Flask(__name__).test_request_context("/?format=csv&table=summary"):
        resp, _ = execution._csv_response(oqo, _summary_body(oqo, (True, True)), A.price(oqo))
    assert resp.headers["X-More-Groups-Splits"] == "1:by-author.csv:13,2:by-year.csv:"


def test_a_whole_summary_names_nothing_to_page():
    oqo = parse_either(OQL)
    with Flask(__name__).test_request_context("/?format=csv&table=summary"):
        resp, _ = execution._csv_response(oqo, _summary_body(oqo, (False, False)), A.price(oqo))
    assert "X-More-Groups-Splits" not in resp.headers and "X-Groups-Note" not in resp.headers


def test_a_split_page_carries_the_next_cursor_and_its_rows():
    oqo = parse_either(OQL)
    page = {"meta": {"measures": [COUNT], "splits": [analytics_csv.split_meta(oqo.group_by[0], "works")],
                     "groups_count": 13, "rows_count": 13, "next_cursor": "g1.abc", "more_groups": True},
            "summary": {"all": {"key": "all", "count": 16}},
            "group_by": [{"key": "https://openalex.org/A0001", "key_display_name": "A1", "count": 3}]}
    with Flask(__name__).test_request_context("/?format=csv&table=summary&split=1&cursor=*"):
        resp, _ = execution._csv_response(oqo, page, A.price(oqo), paging=True, split=1)
    assert resp.headers["X-Next-Cursor"] == "g1.abc" and resp.headers["X-Rows"] == "1"
    assert resp.headers["X-Groups-Count"] == "13" and "X-More-Groups-Splits" not in resp.headers
    assert _read(resp.get_data(as_text=True)) == [["author", "author id", "count"], ["A1", "A0001", "3"]]
