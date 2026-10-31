"""Two page views that ran near the 11-second limit live (oxjob #1598, 2026-10-30):

- A key set found by listing the works' groups whole goes to ES as the shorter of its kept and its left-out keys.
  CRISPR authors whose last known institution is not Harvard keep 67,505 of the works' 68,484 authors; the outer
  listing took 3.3 s with them as include and 0.5 s with the other 979 as exclude, the same rows. Over a set of
  fewer than PARTITION_MIN_WORKS works the works' groups are listed with the map hint (0.5 s vs 1.6-1.9 s).
- Both sides too big to list, with a rare pass (Michigan's 69,125 authors among 44M in works since 2020): the first
  list of the works' groups is sized from the expected pass rate, so it takes one list (3 s) instead of two.

Fakes: test_nested_pages.FakeES (the works) and test_both_sides_checked_as_read.OwnES (the authors' own index)."""
from dataclasses import replace

import pytest

from query_translation import analytics as A
from tests.oql.test_both_sides_checked_as_read import (NESTED, SINGLE, OwnES, _both_sides_big, _nested_truth, _run,
                                                       _truth)
from tests.oql.test_nested_pages import WORKS, _leaves, _norm, _a

HELD = {k for au, _ in WORKS for k in au}   # the 13 authors the works hold
MOST = HELD - {_a(3), _a(9)}                # most pass: the 2 left out go as exclude
FEW = {_a(1), _a(2), _a(4)}                 # few pass: the 3 kept go as include


def _works_side_listed(monkeypatch, n_works=len(WORKS)):
    """The own side too big to list, the works' groups few enough: they're listed and checked."""
    _both_sides_big(monkeypatch, n_own=10 ** 6, n_keys=len(HELD), n_works=n_works, works_side_limit=10 ** 6)


def _key_set_terms(fake):
    """The terms of every works request carrying the split's key set (include or exclude)."""
    out = []

    def walk(aggs):
        for a in (aggs or {}).values():
            t = a.get("terms") or {}
            if isinstance(t.get("include"), list) or t.get("exclude"):
                out.append(t)
            walk(a.get("aggs"))
    for kind, body in fake.calls:
        if kind == "search":
            walk(body.get("aggs"))
    return out


@pytest.mark.parametrize("own,sent", [(MOST, "exclude"), (FEW, "include")])
def test_a_single_split_sends_the_shorter_list_and_answers_the_same(monkeypatch, own, sent):
    _works_side_listed(monkeypatch)
    fake = OwnES(WORKS, own)
    body = _run(monkeypatch, fake, per_page=100)
    assert [(g["key"], g["count"]) for g in body["group_by"]] == _truth(own)
    assert body["meta"]["groups_count"] == len(own & HELD)
    # listed whole and most kept: the groups are known, so the main request counts none
    counted = any("n_groups" in (b.get("aggs") or {}) for kind, b in fake.calls if kind == "search")
    assert counted == (sent == "include")
    s0 = [t for t in _key_set_terms(fake) if "author" in t["field"]]
    assert s0 and all(sent in t for t in s0)
    if sent == "exclude":
        assert all(sorted(t["exclude"]) == [_a(3), _a(9)] and "include" not in t for t in s0)


@pytest.mark.parametrize("per_page", [1, 3, 5, 100])
def test_a_nested_page_view_with_the_left_out_keys_holds_the_first_rows(monkeypatch, per_page):
    _works_side_listed(monkeypatch)
    body = _run(monkeypatch, OwnES(WORKS, MOST), oql=NESTED, per_page=per_page)
    assert _norm(_leaves(body["group_by"])) == _nested_truth(MOST)[:per_page]


@pytest.mark.parametrize("per_page", [1, 3, 100])
def test_a_nested_cursor_with_the_left_out_keys_walks_every_kept_row(monkeypatch, per_page):
    from tests.oql.test_nested_pages import _walk
    _works_side_listed(monkeypatch)
    rows, _ = _walk(monkeypatch, OwnES(WORKS, MOST), oql=NESTED, per_page=per_page)
    assert [(a, str(y), n) for a, y, n in rows] == sorted(_nested_truth(MOST))


@pytest.mark.parametrize("n_works,min_works,hint", [(16, 2_000_000, True), (3_000_000, 2_000_000, False)])
def test_the_works_groups_are_listed_with_the_map_hint_over_a_small_set(monkeypatch, n_works, min_works, hint):
    _works_side_listed(monkeypatch, n_works=n_works)
    fake = OwnES(WORKS, MOST)
    _run(monkeypatch, fake, min_works=min_works, per_page=100)
    listed = [b["aggs"]["k"]["terms"] for kind, b in fake.calls
              if kind == "search" and "k" in (b.get("aggs") or {}) and "partition" in str(b["aggs"]["k"])]
    assert listed and all((t.get("execution_hint") == "map") == hint for t in listed)


def test_the_key_set_goes_as_the_shorter_list_of_the_works_groups():
    lv = A.Level(index=0, split=None, kind="terms", include={"a", "b", "c"}, universe=frozenset({"a", "b", "c", "d"}))
    assert lv.dropped_keys() == ["d"] and A._keyset_terms(lv) == {"exclude": ["d"]}
    lv = replace(lv, include={"a", "b", "c", "d"})
    assert lv.dropped_keys() == [] and A._keyset_terms(lv) == {}     # every group kept: no filter at all
    lv = replace(lv, include={"a", "b", "c", "x"})                     # x: no work holds it, kept or not
    assert lv.dropped_keys() == ["d"] and A._keyset_terms(lv) == {"exclude": ["d"]}
    assert A._groups_count(lv, {}) == 3                                 # the works' groups less the left-out ones
    lv = replace(lv, include={"a", "b", "c"}, exclude={"b"})           # an excluded key leaves the kept list
    assert lv.dropped_keys() == ["b", "d"] and A._keyset_terms(lv) == {"include": ["a", "c"]}
    assert A._keyset_terms(replace(lv, universe=None, include={"a"}, exclude=None)) == {"include": ["a"]}


@pytest.mark.parametrize("n_own,n_keys,first", [(8, 10 ** 6, "OWN_CANDIDATES_MAX"), (8, 13, "OWN_CANDIDATES_FIRST")])
def test_a_rare_pass_gets_a_long_first_list(monkeypatch, n_own, n_keys, first):
    _both_sides_big(monkeypatch, n_own=n_own, n_keys=n_keys)
    fake = OwnES(WORKS)
    body = _run(monkeypatch, fake, per_page=2)
    assert body["group_by"]
    sizes = [b["aggs"]["c"]["terms"]["size"] for kind, b in fake.calls
             if kind == "search" and "c" in (b.get("aggs") or {})]
    assert sizes == [getattr(A, first)]   # one list either way
