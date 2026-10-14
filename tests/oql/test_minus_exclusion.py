"""A minus glued to a search word or quoted phrase excludes it (oxjob #1683).

People exclude Google-style: `has (asthma -mice)`. OQL used to fold `-mice` into
the stemmed run, so the engine searched `asthma mice` (live 2026-10-14: 18,205,
the AND set, vs 379,186 for `asthma and not mice`), and `-"animal model"` lexed
as a lone `-` word plus a required phrase. Now `-word` reads as `not word` and
`-"phrase"` as `not "phrase"`, echoed in the canonical `and not` form.

What stays text: a hyphen inside a word (`covid-19`, `t-cell`, `x-ray`), a minus
before a digit (`-19`), a spaced ` - `, and anything inside quotes.

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_minus_exclusion.py -q --noconftest
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation.oql_lang import parse, render_tree, OQLError  # noqa: E402
from query_translation.oql_parser import parse_either  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402

TA = "title_and_abstract.search"
TITLE = "display_name.search"


def _rows(oql):
    return parse(oql).to_dict()["filter_rows"]


def _leaf(column, value, negated=False):
    leaf = {"column_id": column, "value": value, "operator": "has"}
    if negated:
        leaf["is_negated"] = True
    return leaf


def _echo(oql):
    """The echo in the person's own order (decision 30), checked to re-parse to the same
    OQO and to be canonically the same query as its `and not` spelling."""
    oqo = parse(oql)
    out = render_tree(oqo, resolver=None)[0]
    assert parse(out).to_dict() == oqo.to_dict(), f"OQO identity broken for {oql!r}"
    assert render_tree(parse(out), resolver=None)[0] == out, f"render not idempotent for {oql!r}"
    assert canonicalize_oqo(oqo).to_dict() == canonicalize_oqo(parse(out)).to_dict()
    return out


# --- a minus word or phrase is `not` ----------------------------------------- #

def test_minus_word_is_not():
    assert _rows("works where title/abstract has (asthma -mice)") == [
        _leaf(TA, "asthma"), _leaf(TA, "mice", negated=True)]
    assert _rows("works where title/abstract has (asthma -mice)") == _rows(
        "works where title/abstract has (asthma and not mice)")


def test_minus_phrase_is_not_phrase():
    # was `asthma - AND "animal model"`: the phrase became required
    assert _rows('works where title/abstract has (asthma -"animal model")') == [
        _leaf(TA, "asthma"), _leaf(TA + ".exact", '"animal model"', negated=True)]


def test_minus_negates_one_word_not_the_run():
    assert _rows("works where title has (-machine learning)") == [
        _leaf(TITLE, "machine", negated=True), _leaf(TITLE, "learning")]


def test_several_minus_words():
    assert _rows("works where title has (asthma -mice -rats)") == [
        _leaf(TITLE, "asthma"), _leaf(TITLE, "mice", negated=True),
        _leaf(TITLE, "rats", negated=True)]


def test_minus_word_after_an_explicit_connective():
    assert _rows("works where title has (asthma or -mice)") == _rows(
        "works where title has (asthma or not mice)")


def test_minus_word_alone_and_without_parens():
    assert _rows("works where title has -mice") == [_leaf(TITLE, "mice", negated=True)]
    assert _rows("works where title has (-mice)") == [_leaf(TITLE, "mice", negated=True)]


def test_minus_on_stemmed_phrase_and_wildcard():
    assert _rows('works where title has (cancer -stemmed "animal model")')[1] == _leaf(
        TITLE, '"animal model"', negated=True)
    assert _rows("works where title has (asthma -adolescen*)")[1] == _leaf(
        TITLE + ".exact", "adolescen*", negated=True)


def test_two_terms_without_parens_still_need_them():
    with pytest.raises(OQLError) as e:
        parse("works where title has asthma -mice")
    assert e.value.code == "OQL_UNDELIMITED_TERM_LIST"


@pytest.mark.parametrize("oql,echo", [
    ("works where title/abstract has (asthma -mice)",
     "works where title-abstract has (asthma and not mice)"),
    ('works where title/abstract has (asthma -"animal model")',
     'works where title-abstract has (asthma and not "animal model")'),
    ("works where title has (t-cell -x-ray)",
     "works where title has (t-cell and not x-ray)"),
])
def test_echo_says_not_and_round_trips(oql, echo):
    assert _echo(oql) == echo


def test_core_sentence_reads_the_minus_too():
    rows = parse_either("get works about (asthma -mice)").to_dict()["filter_rows"]
    assert rows == [_leaf("title_abstract_keywords.search", "asthma"),
                    _leaf("title_abstract_keywords.search", "mice", negated=True)]


# --- what stays text --------------------------------------------------------- #

@pytest.mark.parametrize("oql,value", [
    ("works where title has (covid-19 vaccine)", "covid-19 vaccine"),
    ("works where title has (t-cell x-ray)", "t-cell x-ray"),
    ("works where title has (asthma -19)", "asthma -19"),      # a minus before a digit
    ("works where title has (asthma - mice)", "asthma - mice"),  # a spaced dash
])
def test_hyphens_digits_and_dashes_stay_text(oql, value):
    assert _rows(oql) == [_leaf(TITLE, value)]


def test_minus_inside_quotes_stays_text():
    assert _rows('works where title has ("e -learning")') == [
        _leaf(TITLE + ".exact", '"e -learning"')]
