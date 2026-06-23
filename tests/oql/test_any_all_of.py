"""`any` / `all` keyword groups are GONE — boolean groups use bare parens (#503).

Decisions 31 + 32 briefly made `any (a, b)` / `all (a, b)` the canonical group
form; #503 reverted that. The canonical (and only) group form is now the infix
parens bag: `<op> (a or b)` / `<op> (a and b)`, nesting freely. `any` / `all` are
ordinary value/search words again — they no longer open a group, so a literal
`is any (a, b)` is just a bad undelimited list and hard-errors.

Run with:
    PYTHONPATH=. pytest tests/oql/test_any_all_of.py -q
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation.oql_lang import parse, render, OQLError  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402


def _oqo(oql):
    return canonicalize_oqo(parse(oql)).to_dict()


def _err(oql):
    with pytest.raises(OQLError) as ei:
        parse(oql)
    return ei.value.code


# --- the parens bag is canonical; both joins, both operators ------------------ #

@pytest.mark.parametrize("oql", [
    "works where type is (article or review)",
    "works where type is (article and review)",
    "works where title has (cat or dog)",
    "works where title has (cat and dog)",
    "works where author is (A5023888391 and A5017898742)",
])
def test_parens_form_round_trips(oql):
    assert render(parse(oql)) == oql


def test_render_is_infix_not_keyword():
    out = render(parse("works where type is (article or review)"))
    assert out == "works where type is (article or review)"
    assert "any (" not in out and "all (" not in out


# --- nesting: parens nest freely both ways ------------------------------------ #

def test_parens_nest_freely():
    assert _oqo("works where title has (foo and (bar or baz))") == \
        _oqo("works where title has (foo and (bar or baz))")
    # same-join nesting flattens
    assert _oqo("works where type is (a or (b or c))") == \
        _oqo("works where type is (a or b or c)")


# --- single item unwraps ------------------------------------------------------- #

def test_single_item_unwraps():
    assert _oqo("works where type is (article)") == \
        _oqo("works where type is article")


# --- negation lives on leaves, inside the group ------------------------------- #

def test_negated_leaves_inside_a_group():
    assert _oqo("works where institution is (not I33213144 or I97018004)") == \
        _oqo("works where institution is (not I33213144 or I97018004)")
    # "none of A, B" = (not A and not B)
    assert _oqo("works where institution is (not I33213144 and not I97018004)") == \
        _oqo("works where institution is (not I33213144 and not I97018004)")


def test_bare_paren_group_negation_still_works():
    """`is not (a or b)` is unchanged (decision 23): it parses (De Morgan pushes
    negation to the leaves)."""
    parse("works where institution is not (I33213144 or I97018004)")  # no raise


# --- guardrail: one separator per level (or/and, never commas) ---------------- #

def test_no_commas_inside_a_group():
    assert _err("works where type is (article, review)") == "OQL_COMMA_IN_GROUP"


# --- `any` / `all` are plain words and no longer open a group ----------------- #

@pytest.mark.parametrize("oql", [
    "works where type is any (article, review)",
    "works where type is all (article, review)",
    "works where title has any (cat, dog)",
    "works where institution is not any (I33213144, I97018004)",
    "works where type is any of (article, review)",
])
def test_any_all_keyword_groups_are_rejected(oql):
    """`any`/`all` no longer open a group — these are all malformed input."""
    with pytest.raises(OQLError):
        parse(oql)


def test_all_the_things_is_a_plain_run():
    # a bare run, no parens -> the arity rule (D1) still requires 2+ to be grouped
    assert _err("works where title has all the things") == "OQL_UNDELIMITED_TERM_LIST"
    # a single bare value / quoted phrase that merely contains the word is fine
    parse('works where title has "all of the above"')  # quoted phrase, no raise


# --- the any/all migration diagnostics are gone ------------------------------- #

def test_diagnostic_registry_has_no_any_all_codes():
    from query_translation.diagnostics import DIAGNOSTICS
    assert "OQL_LIST_KEYWORD_REMOVED" not in DIAGNOSTICS
    assert "OQL_NEGATED_LIST_KEYWORD" not in DIAGNOSTICS
    assert "OQL_ANY_OF_RENAMED" not in DIAGNOSTICS
