"""`^` and token-leading `+`/`-` no longer block the exact-value token split, and a
mixed phrase+words value lifts to its implicit AND (oxjob #633, session 8).

Engine facts this encodes (prod, 2026-08-22, title_and_abstract.search.exact):

    cancer treatment             1,815,982   AND-of-words baseline
    +cancer -treatment           1,815,982   plain path: `+`/`-` are punctuation
    machine 3 learning             229,325
    machine^3 learning             229,325   plain path: `^` is punctuation, `3` a word
    has ("+cancer -treatment")     199,107   the OLD phrase render — a different query
    has ("machine^3 learning")           0   ditto

and since core/search.py now escapes `- + ^ { } &` outside quotes on the
query_string branches too, they are literal text at every door, so the
per-token leaves are result-preserving everywhere.

Mixed values (`"machine learning" neural`) used to stay ONE leaf the renderers
could not spell: stemmed dropped the quotes (314,033 vs 1,189,845), exact
nested them (`(""machine learning" neural")`, unparseable). They now lift
through the boolean tokenizer as the implicit AND they are on the engine.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_exact_operator_split.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.oql_lang import split_exact_words  # noqa: E402
from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402
from query_translation.oql_renderer import render_oqo_to_oql  # noqa: E402
from query_translation.url_parser import _is_mixed_phrase_value, parse_url_to_oqo  # noqa: E402
from query_translation.url_renderer import render_oqo_to_url  # noqa: E402

EXACT = "title_and_abstract.search.exact"
STEM = "title_and_abstract.search"


def _rows(oqo):
    return oqo.to_dict()["filter_rows"]


def _scoped(param, value):
    return parse_url_to_oqo("works", scoped_searches={param: value})


# --- the splitter ---------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("machine^3 learning", ["machine^3", "learning"]),
    ("+cancer -treatment", ["+cancer", "-treatment"]),
    ("cancer -treatment", ["cancer", "-treatment"]),
    ("x^2 y", ["x^2", "y"]),
    ("Small -Farm Technical", ["Small", "-Farm", "Technical"]),   # real pasted-title shape
])
def test_operator_shaped_tokens_now_split(value, expected):
    assert split_exact_words(value) == expected


@pytest.mark.parametrize("value", [
    "machine~2 learning",   # fuzzy — documented, honored
    '"a b" c',              # quotes are syntax (lifted upstream instead)
    "a|b c",                # OR-pipe is split upstream
    "(a b) c",              # parens
    "a [b TO c]",
    "Windows AND DLL",      # operator word
    "a && b",               # `&` stays banned (a lone `&&` leaf is meaningless)
])
def test_structural_values_still_refuse(value):
    assert split_exact_words(value) is None


# --- both legs round-trip the split --------------------------------------------

CASES = ["machine^3 learning", "+cancer -treatment", "Small -Farm Technical"]


@pytest.mark.parametrize("value", CASES)
def test_exact_param_parses_to_per_token_leaves(value):
    assert [r["value"] for r in _rows(_scoped("search.title_and_abstract.exact", value))] == value.split()


@pytest.mark.parametrize("value", CASES)
def test_filter_door_agrees_with_param_door(value):
    assert _rows(_scoped("search.title_and_abstract.exact", value)) == _rows(
        parse_url_to_oqo("works", filter_string=f"{EXACT}:{value}"))


@pytest.mark.parametrize("value", CASES)
def test_url_leg_round_trips(value):
    oqo = _scoped("search.title_and_abstract.exact", value)
    assert _rows(parse_url_to_oqo("works", filter_string=render_oqo_to_url(oqo)["filter"])) == _rows(oqo)


@pytest.mark.parametrize("value", CASES)
def test_oql_leg_round_trips_and_is_the_quoted_and(value):
    oqo = _scoped("search.title_and_abstract.exact", value)
    oql = render_oqo_to_oql(oqo)
    assert oql == "works where title/abstract has (" + " and ".join(f'"{t}"' for t in value.split()) + ")"
    assert _rows(parse_oql_to_oqo(oql)) == _rows(oqo)


# --- mixed phrase + bare words --------------------------------------------------

@pytest.mark.parametrize("value,mixed", [
    ('"machine learning" neural', True),
    ('"machine learning" -neural', True),
    ('neural "machine learning"', True),
    ('"a b"~3 word', True),
    ('"machine learning"', False),          # pure phrase
    ('"a b"~3', False),                     # pure proximity
    ('"a"~3~"b"', False),                   # binary proximity
    ("machine learning", False),            # no quotes
    ('a "b', False),                        # odd quotes — not a phrase
])
def test_mixed_phrase_detector(value, mixed):
    assert _is_mixed_phrase_value(value) is mixed


def test_mixed_value_lifts_on_the_exact_door():
    oqo = _scoped("search.title_and_abstract.exact", '"machine learning" -neural')
    assert _rows(oqo) == [
        {"column_id": EXACT, "value": '"machine learning"', "operator": "has"},
        {"column_id": EXACT, "value": "-neural", "operator": "has"},
    ]
    oql = render_oqo_to_oql(oqo)
    assert oql == 'works where title/abstract has ("machine learning" and "-neural")'
    assert _rows(parse_oql_to_oqo(oql)) == _rows(oqo)
    assert _rows(parse_url_to_oqo("works", filter_string=render_oqo_to_url(oqo)["filter"])) == _rows(oqo)


def test_mixed_value_lifts_on_the_stemmed_door():
    oqo = _scoped("search.title_and_abstract", '"machine learning" neural')
    assert _rows(oqo) == [
        {"column_id": STEM, "value": '"machine learning"', "operator": "has"},
        {"column_id": STEM, "value": "neural", "operator": "has"},
    ]
    oql = render_oqo_to_oql(oqo)
    assert oql == 'works where title/abstract has (stemmed "machine learning" and neural)'
    assert _rows(parse_oql_to_oqo(oql)) == _rows(oqo)
    assert _rows(parse_url_to_oqo("works", filter_string=render_oqo_to_url(oqo)["filter"])) == _rows(oqo)


def test_pure_phrase_still_one_leaf():
    oqo = _scoped("search.title_and_abstract.exact", '"machine learning"')
    assert _rows(oqo) == [{"column_id": EXACT, "value": '"machine learning"', "operator": "has"}]
