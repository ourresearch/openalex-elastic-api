"""Nested splits past the limits whose groups are filtered on their own records (oxjob #1598, 2026-10-29): `by journal
and year`, `by institution in [Canada](CA) and subfield`, `by author where last known institution is not [X] and
year`. The filter is a key set (`lv.include` / `lv.exclude`); the page view's terms aggregations take it as include /
exclude, and the cursor's composite can't, so its rows outside a key set are dropped as they are read and a leading
split with an include list pages through its own sorted keys. The fake ES is test_nested_pages.FakeES; the live
checks against production are in the job's EXPLORE.md."""
import itertools
from collections import Counter
from dataclasses import replace

import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either
from tests.oql.test_nested_pages import WORKS, FakeES, _a, _leaves, _setup, _walk

BY_AUTHOR_AND_YEAR = ("get the count of all works by author where last known institution is "
                      "[Harvard University](I136199984) and year")
BY_YEAR_AND_AUTHOR = ("get the count of all works by year and author where last known institution is "
                      "[Harvard University](I136199984)")
KEPT = {_a(1), _a(2), _a(9), _a(13)}


def _keyset(monkeypatch, include=None, exclude=None):
    """The authors' own-field lookup, faked: the split by author keeps `include` (or leaves out `exclude`)."""
    def resolve(lv, parts, oqo, *a, **k):
        lv.include, lv.exclude = include, exclude
        return []
    monkeypatch.setattr(A, "resolve_keysets", resolve)


def _rows(rows):
    return [(str(a), str(b), n) for a, b, n in rows]


def _exact(keep, author_first=True):
    counts = Counter(c for au, ys in WORKS for c in itertools.product(au, ys))
    return sorted(((a, str(y)) if author_first else (str(y), a)) + (n,) for (a, y), n in counts.items() if keep(a))


def _page(monkeypatch, oql, per_page=100):
    fields_dict = _setup(monkeypatch, FakeES(WORKS))
    return A.run(parse_either(oql), index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, per_page=per_page)


@pytest.mark.parametrize("per_page", [1, 2, 3, 7, 100])
@pytest.mark.parametrize("chunk", [1, 2, 100])
def test_a_leading_key_set_walks_its_own_keys_exactly(monkeypatch, per_page, chunk):
    fake = FakeES(WORKS)
    _keyset(monkeypatch, include=set(KEPT))
    monkeypatch.setattr(A, "KEYSET_CHUNK", chunk)
    monkeypatch.setattr(A, "NESTED_MIN_TERMS", 1)
    rows, _ = _walk(monkeypatch, fake, oql=BY_AUTHOR_AND_YEAR, per_page=per_page)
    assert _rows(rows) == _exact(lambda a: a in KEPT)
    # its keys come from the key set, not the index-wide term list, and each range is a terms filter on them
    assert not any(c[0] == "terms_enum" for c in fake.calls)
    assert any("terms" in f for c in fake.calls if c[0] == "search"
               for f in ((c[1].get("query") or {}).get("bool") or {}).get("filter") or [])


def test_a_small_set_with_a_leading_key_set_still_walks_its_keys(monkeypatch):
    _keyset(monkeypatch, include=set(KEPT))
    rows, _ = _walk(monkeypatch, FakeES(WORKS), oql=BY_AUTHOR_AND_YEAR, per_page=2, min_works=10 ** 9)
    assert _rows(rows) == _exact(lambda a: a in KEPT)


@pytest.mark.parametrize("per_page", [1, 2, 5, 100])
def test_a_left_out_key_set_drops_its_rows_and_keeps_every_other(monkeypatch, per_page):
    _keyset(monkeypatch, exclude={_a(2), _a(9)})
    rows, _ = _walk(monkeypatch, FakeES(WORKS), oql=BY_AUTHOR_AND_YEAR, per_page=per_page)
    assert _rows(rows) == _exact(lambda a: a not in {_a(2), _a(9)})


@pytest.mark.parametrize("per_page", [1, 2, 3, 100])
@pytest.mark.parametrize("keyset", [True, False])
def test_a_year_leading_a_big_set_walks_every_row(monkeypatch, per_page, keyset):
    # until 2026-10-29 `... since 2024 by year and institution` with cursor=* exported 0 rows and no cursor: ES
    # terms-enum answers an empty list on a number field, read as "no keys left"; a year reads as one range
    fake = FakeES(WORKS)
    if keyset:
        _keyset(monkeypatch, include=set(KEPT))
    rows, _ = _walk(monkeypatch, fake, oql=BY_YEAR_AND_AUTHOR if keyset else
                    "get the count of all works by year and author", per_page=per_page)
    assert _rows(rows) == _exact((lambda a: a in KEPT) if keyset else (lambda a: True), author_first=False)
    assert not any(c[0] == "terms_enum" for c in fake.calls)


def test_terms_enum_lists_keyword_keys_only(monkeypatch):
    class Conn:
        calls = 0

        def __init__(self, answer):
            self.answer = answer

        def terms_enum(self, **params):
            Conn.calls += 1
            return self.answer
    import elasticsearch_dsl.connections as C
    for answer, want in (({"terms": [], "complete": True}, ([], True)),       # no keys left
                         ({"terms": [], "complete": False}, None),            # cut short: says nothing
                         ({"terms": ["a", "b"], "complete": False}, (["a", "b"], False))):
        monkeypatch.setattr(C, "get_connection", lambda c=None, a=answer: Conn(a))
        assert A._terms_after("works", None, "f", None, 5, A.Deadline()) == want
    before = Conn.calls
    assert A._terms_after("works", None, "publication_year", None, 5, A.Deadline(), "number") is None
    assert Conn.calls == before          # not asked: ES answers [] on a number field


def test_the_page_view_of_a_key_set_split_holds_only_its_groups(monkeypatch):
    _keyset(monkeypatch, include=set(KEPT))
    body = _page(monkeypatch, BY_AUTHOR_AND_YEAR)
    rows = _leaves(body["group_by"])
    assert sorted(_rows(rows)) == _exact(lambda a: a in KEPT)
    m = body["meta"]
    assert m["more_groups"] is True
    assert m["groups_count"] == len(KEPT)          # the key set's own keys, not the 13 authors the works hold
    assert m["rows_count"] == len(rows)            # the combinations, counted under the key set's keys


def test_the_page_view_of_an_inner_key_set_holds_only_its_groups(monkeypatch):
    _keyset(monkeypatch, exclude={_a(1)})
    rows = _leaves(_page(monkeypatch, BY_YEAR_AND_AUTHOR)["group_by"])
    assert sorted(_rows(rows)) == _exact(lambda a: a != _a(1), author_first=False)


def test_a_calculation_filter_on_an_outer_split_still_refuses(monkeypatch):
    with pytest.raises(A.AnalyticsError) as e:
        _page(monkeypatch, "get the count of all works by author and year. Only authors with at least 2 works.", 3)
    assert e.value.code == "too_many_groups"


def test_a_key_set_holds_at_most_its_own_keys_and_sorts_them_once():
    lv = A.Level(index=0, split=None, kind="terms", include={"c", "a", "b"}, exclude={"b"})
    assert lv.kept_keys() == ["a", "c"] and lv.kept_keys() is lv.kept_keys()
    assert lv.keeps("a") and not lv.keeps("b") and not lv.keeps("z")
    lv.include = {"z"}                              # replaced: sorted again
    assert lv.kept_keys() == ["z"]
    assert A._keyset_terms(lv) == {"include": ["z"]}
    assert A._keyset_terms(A.Level(index=0, split=None, kind="terms", include=set())) == {"include": ["__none__"]}
    assert A._keyset_terms(A.Level(index=0, split=None, kind="terms", exclude={"b"})) == {"exclude": ["b"]}
    cards = {0: 100, 1: 5}
    A._cap_cards(cards, {0: 7, 1: None})
    assert cards == {0: 7, 1: 5}


def test_keys_after_lists_a_sorted_key_set_past_a_key():
    keys = ["a", "c", "e", "g"]
    assert A._keys_after(keys, None, 2) == ["a", "c"]
    assert A._keys_after(keys, "c", 2) == ["e", "g"]
    assert A._keys_after(keys, "b", 10) == ["c", "e", "g"]
    assert A._keys_after(keys, "g", 2) == []
