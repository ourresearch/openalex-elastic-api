"""oxjob #400 — raw affiliation search is exact-only.

Its ES field (`authorships.raw_affiliation_strings`, standard analyzer) was never
stemmed, so `raw_affiliation_strings.search` named a mode it didn't have. The honest
name is `raw_affiliation_strings.search.exact`; `.search` stays accepted as its alias
(`alternate_of`). Behavior is unchanged: both run the same engine query, and query
translation keeps a raw-affiliation search as ONE value with the user's quotes, as the
`.search` spelling always ran (quotes on `Paris-Saclay` make a phrase there: 162,495
works live vs 184,312 bare, 2026-11-03).

    PYTHONPATH=. pytest tests/oql/test_raw_affiliation_exact_only.py -q
"""
import pytest

from query_translation import oql_lang as L
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_parser import parse_url_to_oqo

EXACT = "raw_affiliation_strings.search.exact"


def _leaves(oqo):
    return [(f.column_id, f.value, bool(f.is_negated)) for f in oqo.filter_rows]


def _url(filter_string):
    return canonicalize_oqo(parse_url_to_oqo("works", filter_string=filter_string))


def _rt(oql):
    start = canonicalize_oqo(L.parse(oql))
    rendered = L.render(start)
    back = canonicalize_oqo(L.parse(rendered))
    return rendered, start.to_dict() == back.to_dict()


# ---- the old and new URL spellings are one query ------------------------------

@pytest.mark.parametrize("value", [
    '"universiteit maastricht"',
    "universiteit maastricht",
    "library",
    '"Paris-Saclay"',
    "Paris-Saclay",
    '"london"~5~"hospital"',
    "process*",
    '"dept of chemistry" AND ucla',
    "!universiteit maastricht",
    'teacher!"academic teacher"',
    "a|b",
])
def test_old_and_new_spelling_give_one_oqo(value):
    old = _url(f"raw_affiliation_strings.search:{value}")
    new = _url(f"{EXACT}:{value}")
    assert old.to_dict() == new.to_dict()
    cols = {c for c in _column_ids(new.filter_rows)}
    assert cols == {EXACT}, cols


def _column_ids(rows):
    for f in rows:
        if hasattr(f, "filters"):
            yield from _column_ids(f.filters)
        else:
            yield f.column_id


def test_a_bare_run_stays_one_value():
    # never split per word, unlike the other exact columns
    assert _leaves(_url(f"{EXACT}:universiteit maastricht")) == [
        (EXACT, "universiteit maastricht", False)]


def test_quotes_kept_only_where_they_make_a_phrase():
    assert _leaves(_url(f'{EXACT}:"Paris-Saclay"')) == [(EXACT, '"Paris-Saclay"', False)]
    assert _leaves(_url(f'{EXACT}:"Nigeria"')) == [(EXACT, "Nigeria", False)]
    assert _leaves(_url(f'{EXACT}:"process*"')) == [(EXACT, "process*", False)]


# ---- OQL offers and renders only the exact column -----------------------------

@pytest.mark.parametrize("oql, column_value, rendered", [
    ('works where raw affiliation has ("universiteit maastricht")',
     '"universiteit maastricht"',
     'works where raw affiliation has ("universiteit maastricht")'),
    ("works where raw affiliation has (universiteit maastricht)",
     "universiteit maastricht",
     "works where raw affiliation has (universiteit maastricht)"),
    ('works where raw affiliation has (Nigeria)', "Nigeria",
     'works where raw affiliation has (Nigeria)'),
    ('works where raw affiliation has ("Paris-Saclay")', '"Paris-Saclay"',
     'works where raw affiliation has ("Paris-Saclay")'),
    ('works where raw affiliation has (stemmed "universiteit maastricht")',
     '"universiteit maastricht"',
     'works where raw affiliation has ("universiteit maastricht")'),
    ("works where raw affiliation has (within 5 (london, hospital))",
     '"london"~5~"hospital"',
     "works where raw affiliation has (within 5 (london, hospital))"),
    ('works where raw affiliation has (within 5 ("st thomas", hospital))',
     '"st thomas"~5~"hospital"',
     'works where raw affiliation has (within 5 ("st thomas", hospital))'),
    ("works where raw affiliation has (not universiteit maastricht)",
     "universiteit maastricht",
     "works where raw affiliation has (not universiteit maastricht)"),
])
def test_oql_parses_to_the_exact_column_and_round_trips(oql, column_value, rendered):
    oqo = canonicalize_oqo(L.parse(oql))
    assert [(f.column_id, f.value) for f in oqo.filter_rows] == [(EXACT, column_value)]
    out, identity = _rt(oql)
    assert identity, out
    assert out == rendered
    assert "stemmed" not in out and "near" not in out


def test_old_url_renders_without_near_or_stemmed():
    oqo = _url('raw_affiliation_strings.search:"universiteit maastricht"')
    assert L.render(oqo) == 'works where raw affiliation has ("universiteit maastricht")'


def test_bare_wildcards_need_no_quotes():
    oqo = canonicalize_oqo(L.parse("works where raw affiliation has (process*)"))
    assert _leaves(oqo) == [(EXACT, "process*", False)]


def test_a_run_with_a_wildcard_keeps_it():
    # the bare-run render would read `process*` as punctuation (oxjob #1327), so a
    # multi-word value with a wildcard renders as its quoted word list (same works)
    oqo = _url(f"{EXACT}:process* materials")
    out = L.render(oqo)
    assert "process*" in out
    back = canonicalize_oqo(L.parse(out))
    assert sorted(v for _, v, _ in _leaves(back)) == ["materials", "process*"] \
        or _leaves(back) == [(EXACT, "process* materials", False)]


def test_other_fields_keep_their_stemmed_mode():
    oqo = canonicalize_oqo(L.parse("works where title has (solar cells)"))
    assert [f.column_id for f in oqo.filter_rows] == ["display_name.search"]
    out = L.render(canonicalize_oqo(L.parse('works where title has (stemmed "solar cells")')))
    assert 'stemmed "solar cells"' in out


# ---- a split by raw-affiliation searches still splits --------------------------

def test_split_by_searches_keeps_its_marker():
    q = ('get works where year is (2020); then group those works by raw affiliation '
         'search in ((cnrs), ("max planck"))')
    oqo = canonicalize_oqo(L.parse(q))
    g = oqo.group_by[0]
    assert g.column_id == "raw_affiliation_strings.search"
    assert [v.column_id for v in g.values] == [EXACT, EXACT]
    out, identity = _rt(q)
    assert identity, out


# ---- engine: .search.exact behaves exactly as .search did ----------------------

def test_engine_treats_exact_as_a_search():
    from core.search import check_is_search_query
    assert check_is_search_query([{EXACT: "cnrs"}], None)
    from query_translation.execution import PREFERENCE_SEARCH_COLUMNS
    assert EXACT in PREFERENCE_SEARCH_COLUMNS
    from core.shared_view import SEARCH_FILTER_KEYS
    assert EXACT in SEARCH_FILTER_KEYS


def test_engine_builds_the_same_query_for_both_names():
    from works.fields import fields_dict
    for value in ["universiteit maastricht", '"Paris-Saclay"', '"london"~5~"hospital"']:
        a = fields_dict["raw_affiliation_strings.search"]
        a.value = value
        b = fields_dict[EXACT]
        b.value = value
        assert a.build_query().to_dict() == b.build_query().to_dict(), value


def test_catalog_lists_only_the_exact_name():
    from core.properties import ENTITY_PROPERTIES, stemless_search_columns
    assert stemless_search_columns() == frozenset({EXACT})
    assert ENTITY_PROPERTIES["works"]["raw_affiliation_strings.search"].alternate_of == EXACT


# ---- URL round trips ----------------------------------------------------------

def test_oql_to_url_and_back_keeps_the_query():
    from query_translation.url_renderer import render_oqo_to_url
    for oql in ['works where raw affiliation has ("Paris-Saclay")',
                "works where raw affiliation has (universiteit maastricht)",
                "works where raw affiliation has (within 5 (london, hospital))"]:
        oqo = canonicalize_oqo(L.parse(oql))
        url = render_oqo_to_url(oqo)["filter"]
        assert url.startswith(EXACT + ":"), url
        assert _url(url).to_dict() == oqo.to_dict(), (oql, url)


def test_negated_word_list_comes_back_as_the_same_query():
    # `(not a or not b)` renders the classic compact `field:!a b` (url_renderer's De
    # Morgan form); on raw affiliation that reads back as ONE negated value, NOT(a AND
    # b): the same works, one leaf instead of an OR of two
    from query_translation.url_renderer import render_oqo_to_url
    oqo = canonicalize_oqo(L.parse(
        "works where raw affiliation has (not universiteit or not maastricht)"))
    url = render_oqo_to_url(oqo)["filter"]
    assert url == f"{EXACT}:!maastricht universiteit"   # operands in canonical order
    assert _leaves(_url(url)) == [(EXACT, "maastricht universiteit", True)]
