"""`any` / `all` group sugar — charter decision 31 (#363).

`<op> any (a, b)` ≡ `<op> (a or b)` and `<op> all (a, b)` ≡ `<op> (a and b)`.
`any (` / `all (` are comma-separated group-OPENERS (an atomic keyword + `(`),
usable after `is`/`has` AND nested anywhere a group/operand is — so they're a
one-for-one alias of the parens form and nest the same way. (The openers were
briefly spelled `any of (` / `all of (`; the `of` was dropped because the bare
keyword reads more directly when nesting — the old form now errors
OQL_ANY_OF_RENAMED with a fix-it.)

This is PURE INPUT SUGAR (for now): it parses to the SAME `BranchFilter` the parens
form builds, so the canonicalizer and renderer are untouched and it NEVER round-trips
— `is any (a, b)` re-renders as `is (a or b)`. (That's why the positive forms live
here, not in the canonical corpus, whose `ok` rows are regenerated to canonical.)

Guardrails:
  * one separator per level — commas inside `any`/`all`, `or`/`and` inside a
    bare `(…)`; mixing is OQL_COMMA_IN_GROUP.
  * no operator-negation of a list — there is no `is not any`/`is not all`
    (OQL_NEGATED_LIST_KEYWORD); negate the leaves instead.
  * no trailing comma; `any (a)` unwraps to the bare leaf `a`.
  * `any`/`all` are ordinary words unless immediately followed by `(`
    (`title has all of the above` is a plain search run).

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
    ("works where type is any (article, review)",
     "works where type is (article or review)"),
    ("works where type is all (article, review)",
     "works where type is (article and review)"),
    ("works where title has any (cat, dog)",
     "works where title has (cat or dog)"),
    ("works where title has all (cat, dog)",
     "works where title has (cat and dog)"),
    ("works where author is all (A5023888391, A5017898742)",
     "works where author is (A5023888391 and A5017898742)"),
])
def test_sugar_equals_parens(sugar, parens):
    assert _oqo(sugar) == _oqo(parens)


# --- input-only: it never round-trips; canonical render is the parens form ---- #

def test_sugar_renders_back_as_parens_not_keyword():
    out = render(parse("works where type is any (article, review)"))
    assert out == "works where type is (article or review)"
    assert "any (" not in out and "all (" not in out


# --- nesting: a one-for-one alias of (…), freely mixable both ways ------------ #

def test_keyword_group_nests_inside_parens_and_vice_versa():
    # the charter's worked example
    assert _oqo("works where title has all (foo, any (bar, baz))") == \
        _oqo("works where title has (foo and (bar or baz))")
    # a paren group nesting a keyword group
    assert _oqo("works where title has (foo and any (bar, baz))") == \
        _oqo("works where title has (foo and (bar or baz))")
    # keyword nesting keyword
    assert _oqo("works where type is any (article, all (review, preprint))") == \
        _oqo("works where type is (article or (review and preprint))")


def test_same_join_nesting_flattens_like_parens():
    assert _oqo("works where type is any (a, any (b, c))") == \
        _oqo("works where type is (a or b or c)")


# --- single item unwraps; the keyword adds nothing for one operand ------------ #

def test_single_item_unwraps():
    assert _oqo("works where type is any (article)") == \
        _oqo("works where type is article")
    assert _oqo("works where type is all (article)") == \
        _oqo("works where type is article")


# --- negation lives on leaves, inside the list ------------------------------- #

def test_negated_leaves_inside_a_list():
    assert _oqo("works where institution is any (not I33213144, I97018004)") == \
        _oqo("works where institution is (not I33213144 or I97018004)")
    # "none of A, B" = all (not A, not B) = NOT A AND NOT B
    assert _oqo("works where institution is all (not I33213144, not I97018004)") == \
        _oqo("works where institution is (not I33213144 and not I97018004)")


# --- guardrail: one separator per level -------------------------------------- #

@pytest.mark.parametrize("oql", [
    "works where type is any (article or review)",   # or/and inside a keyword list
    "works where type is all (article and review)",
    "works where type is any (article, review or other)",  # mixed mid-list
])
def test_no_connectives_inside_a_keyword_list(oql):
    assert _err(oql) == "OQL_COMMA_IN_GROUP"


def test_no_commas_inside_a_bare_group():
    assert _err("works where type is (article, review)") == "OQL_COMMA_IN_GROUP"


# --- guardrail: no operator-negation of a list ------------------------------- #

@pytest.mark.parametrize("oql", [
    "works where institution is not any (I33213144, I97018004)",
    "works where institution is not all (I33213144, I97018004)",
])
def test_lists_cannot_be_operator_negated(oql):
    assert _err(oql) == "OQL_NEGATED_LIST_KEYWORD"


def test_bare_paren_group_negation_still_works():
    """`is not (a or b)` is unchanged (decision 23) — only the keyword form is
    blocked. It parses (De Morgan pushes negation to leaves)."""
    parse("works where institution is not (I33213144 or I97018004)")  # no raise


# --- guardrail: no trailing comma; empty list ---------------------------------- #

def test_trailing_comma_is_rejected():
    assert _err("works where type is any (article, review,)") == "OQL_MISSING_VALUE"


def test_empty_list_is_rejected():
    assert _err("works where type is any ()") == "OQL_MISSING_VALUE"


# --- `any`/`all` are plain words unless immediately followed by `(` ----------- #

def test_keyword_only_when_followed_by_paren():
    # bare run, no parens -> the arity rule (D1) still requires 2+ to be grouped
    assert _err("works where title has all the things") == "OQL_UNDELIMITED_TERM_LIST"
    # a single bare value that merely contains the word "of" is fine
    parse('works where title has "all of the above"')  # quoted phrase, no raise


# --- the dropped-`of` form is caught with a migration fix-it ------------------ #

@pytest.mark.parametrize("oql", [
    "works where type is any of (article, review)",
    "works where type is all of (article, review)",
    "works where title has any of (cat, dog)",
    "works where institution is not any of (I33213144, I97018004)",
])
def test_legacy_of_form_errors_with_rename_fixit(oql):
    assert _err(oql) == "OQL_ANY_OF_RENAMED"


def test_all_of_without_paren_is_a_plain_run_not_the_rename_error():
    """`all of (` triggers the rename error, but `all of the above` (no paren) is
    just ordinary words — the rename detector must not fire on it."""
    assert _err("works where title has all of the things") == "OQL_UNDELIMITED_TERM_LIST"


# --- the removed migration error is gone; the new codes exist ----------------- #

def test_diagnostic_registry_reflects_decision_31():
    from query_translation.diagnostics import DIAGNOSTICS
    assert "OQL_LIST_KEYWORD_REMOVED" not in DIAGNOSTICS
    assert "OQL_NEGATED_LIST_KEYWORD" in DIAGNOSTICS
    assert "OQL_ANY_OF_RENAMED" in DIAGNOSTICS
