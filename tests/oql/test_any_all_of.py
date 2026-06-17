"""`any of` / `all of` group sugar — charter decision 31 (#363).

`<op> any of (a, b)` ≡ `<op> (a or b)` and `<op> all of (a, b)` ≡ `<op> (a and b)`.
`any of (` / `all of (` are comma-separated group-OPENERS (atomic two-word
keywords + `(`), usable after `is`/`has` AND nested anywhere a group/operand is —
so they're a one-for-one alias of the parens form and nest the same way.

This is PURE INPUT SUGAR (for now): it parses to the SAME `BranchFilter` the parens
form builds, so the canonicalizer and renderer are untouched and it NEVER round-trips
— `is any of (a, b)` re-renders as `is (a or b)`. (That's why the positive forms live
here, not in the canonical corpus, whose `ok` rows are regenerated to canonical.)

Guardrails:
  * one separator per level — commas inside `any of`/`all of`, `or`/`and` inside a
    bare `(…)`; mixing is OQL_COMMA_IN_GROUP.
  * no operator-negation of a list — there is no `is not any of`/`is not all of`
    (OQL_NEGATED_LIST_KEYWORD); negate the leaves instead.
  * no trailing comma; `any of (a)` unwraps to the bare leaf `a`.
  * `any`/`all`/`of` are ordinary words unless the two keyword words are immediately
    followed by `(` (`title has all of the above` is a plain search run).

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


# --- sugar == the parens form (identical OQO), both joins, both operators ----- #

@pytest.mark.parametrize("sugar, parens", [
    ("works where type is any of (article, review)",
     "works where type is (article or review)"),
    ("works where type is all of (article, review)",
     "works where type is (article and review)"),
    ("works where title has any of (cat, dog)",
     "works where title has (cat or dog)"),
    ("works where title has all of (cat, dog)",
     "works where title has (cat and dog)"),
    ("works where author is all of (A5023888391, A5017898742)",
     "works where author is (A5023888391 and A5017898742)"),
])
def test_sugar_equals_parens(sugar, parens):
    assert _oqo(sugar) == _oqo(parens)


# --- input-only: it never round-trips; canonical render is the parens form ---- #

def test_sugar_renders_back_as_parens_not_any_of():
    out = render(parse("works where type is any of (article, review)"))
    assert out == "works where type is (article or review)"
    assert "any of" not in out and "all of" not in out


# --- nesting: a one-for-one alias of (…), freely mixable both ways ------------ #

def test_keyword_group_nests_inside_parens_and_vice_versa():
    # the charter's worked example
    assert _oqo("works where title has all of (foo, any of (bar, baz))") == \
        _oqo("works where title has (foo and (bar or baz))")
    # a paren group nesting a keyword group
    assert _oqo("works where title has (foo and any of (bar, baz))") == \
        _oqo("works where title has (foo and (bar or baz))")
    # keyword nesting keyword
    assert _oqo("works where type is any of (article, all of (review, preprint))") == \
        _oqo("works where type is (article or (review and preprint))")


def test_same_join_nesting_flattens_like_parens():
    assert _oqo("works where type is any of (a, any of (b, c))") == \
        _oqo("works where type is (a or b or c)")


# --- single item unwraps; the keyword adds nothing for one operand ------------ #

def test_single_item_unwraps():
    assert _oqo("works where type is any of (article)") == \
        _oqo("works where type is article")
    assert _oqo("works where type is all of (article)") == \
        _oqo("works where type is article")


# --- negation lives on leaves, inside the list ------------------------------- #

def test_negated_leaves_inside_a_list():
    assert _oqo("works where institution is any of (not I33213144, I97018004)") == \
        _oqo("works where institution is (not I33213144 or I97018004)")
    # "none of A, B" = all of (not A, not B) = NOT A AND NOT B
    assert _oqo("works where institution is all of (not I33213144, not I97018004)") == \
        _oqo("works where institution is (not I33213144 and not I97018004)")


# --- guardrail: one separator per level -------------------------------------- #

@pytest.mark.parametrize("oql", [
    "works where type is any of (article or review)",   # or/and inside a keyword list
    "works where type is all of (article and review)",
    "works where type is any of (article, review or other)",  # mixed mid-list
])
def test_no_connectives_inside_a_keyword_list(oql):
    assert _err(oql) == "OQL_COMMA_IN_GROUP"


def test_no_commas_inside_a_bare_group():
    assert _err("works where type is (article, review)") == "OQL_COMMA_IN_GROUP"


# --- guardrail: no operator-negation of a list ------------------------------- #

@pytest.mark.parametrize("oql", [
    "works where institution is not any of (I33213144, I97018004)",
    "works where institution is not all of (I33213144, I97018004)",
])
def test_lists_cannot_be_operator_negated(oql):
    assert _err(oql) == "OQL_NEGATED_LIST_KEYWORD"


def test_bare_paren_group_negation_still_works():
    """`is not (a or b)` is unchanged (decision 23) — only the keyword form is
    blocked. It parses (De Morgan pushes negation to leaves)."""
    parse("works where institution is not (I33213144 or I97018004)")  # no raise


# --- guardrail: no trailing comma; empty list ---------------------------------- #

def test_trailing_comma_is_rejected():
    assert _err("works where type is any of (article, review,)") == "OQL_MISSING_VALUE"


def test_empty_list_is_rejected():
    assert _err("works where type is any of ()") == "OQL_MISSING_VALUE"


# --- `any`/`all`/`of` are plain words unless `<kw> of (` follows -------------- #

def test_keyword_only_when_followed_by_paren():
    # bare run, no parens -> the arity rule (D1) still requires 2+ to be grouped
    assert _err("works where title has all of the things") == "OQL_UNDELIMITED_TERM_LIST"
    # a single bare value that merely contains the word "of" is fine
    parse('works where title has "all of the above"')  # quoted phrase, no raise


# --- the removed migration error is gone; OQL_NEGATED_LIST_KEYWORD exists ----- #

def test_diagnostic_registry_reflects_decision_31():
    from query_translation.diagnostics import DIAGNOSTICS
    assert "OQL_LIST_KEYWORD_REMOVED" not in DIAGNOSTICS
    assert "OQL_NEGATED_LIST_KEYWORD" in DIAGNOSTICS
