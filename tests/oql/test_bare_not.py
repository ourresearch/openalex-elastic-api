"""Bare-prefix `not` — charter decision 23 (#363).

`not` is a bare PREFIX keyword: it negates the single value-node immediately
after it, with no parentheses. `not FR`, `not dog`, `not col_x`, `not unknown`.
A run of bare search words is one value-node, so `not machine learning` negates
the whole run. Precedence is the SR/PubMed convention — `not` binds the next
operand only, so `not a or b` = `(not a) or b`. To negate a group, write
`not (a or b)`; the canonicalizer pushes negation down to the leaves (De Morgan).

This REVERSES the functional `not()` (decision 21) and supersedes Change B
(decision 22). There is one negation surface and the canonical render is always
the bare `not <value>` prefix — `is not` / `does not have` /
`is not in collection` are accepted as INPUT aliases but never emitted (the OQO
has no negated-predicate operator; negation only rides the `is_negated` bit).
Booleans, which have no value brick, keep the natural verb flip.

Run with:
    PYTHONPATH=. pytest tests/oql/test_bare_not.py -q
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation.oql_lang import parse, render_tree, OQLError  # noqa: E402,F401
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402


def _identity(oql):
    """render -> reparse -> render must be a fixed point AND OQO-identical."""
    canon = canonicalize_oqo(parse(oql))
    out = render_tree(canon, resolver=None)[0]
    canon2 = canonicalize_oqo(parse(out))
    assert canon.to_dict() == canon2.to_dict(), f"OQO identity broken for {oql!r}"
    out2 = render_tree(canon2, resolver=None)[0]
    assert out == out2, f"render not idempotent for {oql!r}"
    return out


# --- bare `not` is valid everywhere (no OQL_BARE_NOT) ---------------------- #

@pytest.mark.parametrize("oql", [
    "works where country is (not FR and US)",          # inside a value group
    "works where title has (not dog and cat)",    # inside a search group
    "works where title has not dog",              # top search-value slot
    "works where title has (cat and not dog)",    # in-group, second operand
    "works where not (country is FR or type is article)",  # group-negator (clause level)
])
def test_bare_not_parses(oql):
    parse(oql)  # must not raise


def test_bare_not_code_is_gone():
    """OQL_BARE_NOT was removed from the registry (decision 23)."""
    from query_translation.diagnostics import DIAGNOSTICS
    assert "OQL_BARE_NOT" not in DIAGNOSTICS


# --- canonical render is the bare `not <value>` prefix, every kind ---------- #

def test_standalone_negated_leaves_render_bare_prefix():
    assert _identity("works where country is not FR") \
        == "works where country is not FR"
    assert _identity("works where title has not dog") \
        == "works where title has not dog"
    assert _identity("works where work is in collection not col_abc123") \
        == "works where work is in collection not col_abc123"
    assert _identity("works where language is not unknown") \
        == "works where language is not unknown"


def test_in_group_not_renders_bare_prefix():
    assert _identity("works where title has (not dog and cat)") \
        == "works where title has (not dog and cat)"
    assert _identity("works where country is (not FR and US)") \
        == "works where country is (not FR and US)"


def test_no_parens_around_the_negated_atom():
    """The whole point of decision 23: no `not(...)` parens anywhere."""
    out = _identity("works where title has (not dog and cat)")
    assert "not(" not in out and "not (" not in out


# --- not of a group De Morgans to per-atom bare nots ----------------------- #

def test_not_of_a_group_demorgans_to_per_atom_nots():
    assert _identity("works where title has not (dog or cat)") \
        == "works where title has (not cat and not dog)"


def test_not_group_and_x_flattens_with_no_nested_parens():
    out = _identity("works where title has (not (dog or cat) and wombat)")
    assert out == "works where title has (not cat and not dog and wombat)"
    assert "not(" not in out and "not (" not in out


def test_quoted_phrase_negation_round_trips():
    assert _identity('works where title/abstract has (teacher and not "academic teacher")') \
        == 'works where title/abstract has (teacher and not "academic teacher")'


# --- a multi-word search run is ONE value-node that `not` negates whole ----- #

def test_not_negates_a_whole_bare_word_run():
    # `not machine learning` negates the single stemmed run, rendered parenthesized
    # because a multi-token stemmed value is parenthesized (arity rule, §3.6).
    assert _identity("works where title has not machine learning") \
        == "works where title has not (machine learning)"


# --- precedence: `not` binds the next operand only (SR / left-to-right) ----- #

def test_not_binds_next_operand_only():
    # `not a or b` == `(not a) or b`: only the first leaf is negated.
    fr = canonicalize_oqo(parse(
        "works where title has (not a or b)")).to_dict()["filter_rows"]
    # one OR branch of two leaves; only `a` negated
    assert len(fr) == 1 and fr[0]["join"] == "or"
    by_val = {f["value"]: f.get("is_negated", False) for f in fr[0]["filters"]}
    assert by_val == {"a": True, "b": False}


# --- input aliases renormalize to the bare prefix (no predicate survives) --- #

def test_predicate_input_aliases_renormalize_to_bare_prefix():
    assert _identity("works where title does not have dog") \
        == "works where title has not dog"
    assert _identity("works where work is not in collection col_abc123") \
        == "works where work is in collection not col_abc123"
    assert _identity("works where country is not FR") \
        == "works where country is not FR"
    assert _identity("works where country is not (FR or US)") \
        == "works where country is (not FR and not US)"


def test_top_level_not_of_an_or_pushes_to_per_leaf_bare_nots():
    assert _identity("works where not (country is FR or type is article)") \
        == "works where country is not FR and type is not article"


# --- booleans keep the natural verb flip (no value to prefix) --------------- #

def test_booleans_keep_natural_flip():
    assert _identity("works where it's not open access") \
        == "works where it's not open access"
    assert _identity("works where it doesn't have a DOI") \
        == "works where it doesn't have a DOI"
