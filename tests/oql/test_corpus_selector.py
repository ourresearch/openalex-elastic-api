"""Corpus selector (oxjob #481).

The `corpus` OQO field — core / expansion / all — and its OQL parenthetical
surface (`works (all corpora) where …`). Covers the alias spellings that the
corpus.yaml harness can't carry (it requires canonical `oql`), plus the
canonical render, the core-default omission, and the error path.
"""
import pytest

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oqo import OQO, normalize_corpus, VALID_CORPORA


# (oql input, expected canonical corpus value)
ALIAS_CASES = [
    ("works", "core"),
    ("works (core corpus)", "core"),
    ("works (core)", "core"),
    ("works (all corpora)", "all"),
    ("works (all)", "all"),
    ("works (expansion corpus)", "expansion"),
    ("works (expansion)", "expansion"),
    ("works (xpac)", "expansion"),
    ("works (xpac corpus)", "expansion"),
]


@pytest.mark.parametrize("oql,expected", ALIAS_CASES)
def test_corpus_alias_parses(oql, expected):
    assert parse(oql).corpus == expected


@pytest.mark.parametrize("oql,expected", ALIAS_CASES)
def test_corpus_renders_canonically(oql, expected):
    """Every spelling re-renders to ONE canonical form per corpus."""
    rendered = render(parse(oql))
    canonical = {
        "core": "works",
        "all": "works (all corpora)",
        "expansion": "works (expansion corpus)",
    }[expected]
    assert rendered == canonical


def test_core_is_default_and_omitted():
    o = parse("works")
    assert o.corpus == "core"
    assert "(" not in render(o)  # core renders without a parenthetical
    # to_dict omits the default so canonical OQOs stay minimal
    assert "corpus" not in o.to_dict()


def test_non_core_round_trips_through_oqo_dict():
    for corpus in ("all", "expansion"):
        o = OQO(get_rows="works", corpus=corpus)
        assert o.to_dict()["corpus"] == corpus
        assert OQO.from_dict(o.to_dict()).corpus == corpus


def test_corpus_with_where_clause():
    o = parse("works (all corpora) where it's open access")
    assert o.corpus == "all"
    assert len(o.filter_rows) == 1


@pytest.mark.parametrize("bad", [
    "works (banana)",
    "works (banana) where year is 2020",
    "works (",
    "works (full)",          # "full" is intentionally NOT an alias
])
def test_bad_corpus_rejected(bad):
    with pytest.raises(OQLError) as e:
        parse(bad)
    assert e.value.code == "OQL_BAD_CORPUS"


def test_normalize_corpus_helper():
    assert normalize_corpus("ALL Corpora") == "all"   # case/space-insensitive
    assert normalize_corpus("  xpac  ") == "expansion"
    assert normalize_corpus("nonsense") is None
    assert VALID_CORPORA == {"core", "expansion", "all"}
