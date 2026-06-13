"""Functional `not()` — charter decision 21 (#363).

`not` is a FUNCTION: `not(X)`. The parentheses are part of the keyword and they
ARE its scope, so there is no precedence to recall and no `(not (a or b))`
nested-parens ugliness. A **bare `not`** (no following `(`) is an error
(`OQL_BARE_NOT`) everywhere it used to live — at the top level, inside a value
group, and inside a search group.

Predicate negation is UNTOUCHED ("Change A" only): `is not`, `does not contain`,
and boolean negation (`it's not open access` / the bool_false flip) all stay
valid spellings — they are operators, not the bare keyword.

Canonical render pushes negation down to the leaf/value (NNF) and NEVER emits
`not(<whole clause>)`: a standalone negated leaf uses the predicate form
(`title does not contain dog`, `country is not FR`); in-group negation renders
`not(<atom>)` on each negated atom.

Run with:
    PYTHONPATH=. pytest tests/oql/test_functional_not.py -q
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation.oql_lang import parse, render_tree, OQLError  # noqa: E402
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


# --- bare `not` is an error everywhere ------------------------------------- #

@pytest.mark.parametrize("oql", [
    "works where not country is FR",                       # top-level group-negator
    "works where country is (not FR and US)",              # inside a value group
    "works where title contains (not dog and cat)",        # inside a search group
    "works where title contains not dog",                  # top search-value slot
    "works where title contains (cat and not dog)",        # in-group, second operand
])
def test_bare_not_is_an_error(oql):
    with pytest.raises(OQLError) as e:
        parse(oql)
    assert e.value.code == "OQL_BARE_NOT"


# --- not(...) round-trips ---------------------------------------------------- #

def test_in_group_not_renders_functionally():
    assert _identity("works where title contains (not(dog) and cat)") \
        == "works where title contains (not(dog) and cat)"
    assert _identity("works where country is (not(FR) and US)") \
        == "works where country is (not(FR) and US)"


def test_not_of_a_group_demorgans_to_per_atom_nots():
    # NNF pushes negation to the leaves, so `not(a or b)` never renders as a
    # wrapped clause — it becomes `(not(a) and not(b))`.
    assert _identity("works where title contains (not(dog or cat))") \
        == "works where title contains (not(cat) and not(dog))"


def test_quoted_phrase_negation_round_trips():
    assert _identity('works where title/abstract contains (teacher and not("academic teacher"))') \
        == 'works where title/abstract contains (teacher and not("academic teacher"))'


# --- the open sub-question: `does not contain (group)` == `contains not(group)` --- #

def test_predicate_negation_of_a_group_equals_functional_not_of_the_group():
    a = _identity("works where title contains (not(dog or cat))")
    b = _identity("works where title does not contain (dog or cat)")
    assert a == b == "works where title contains (not(cat) and not(dog))"


# --- standalone negation normalizes to the predicate form ------------------- #

def test_standalone_negated_leaf_keeps_predicate_form():
    assert _identity("works where title does not contain dog") \
        == "works where title does not contain dog"
    assert _identity("works where country is not FR") \
        == "works where country is not FR"
    # a `not(...)` written around a single standalone leaf normalizes to it
    assert _identity("works where title contains not(dog)") \
        == "works where title does not contain dog"
    assert _identity("works where not(country is FR)") \
        == "works where country is not FR"


def test_top_level_not_of_an_or_pushes_to_standalone_predicates():
    assert _identity("works where not(country is FR or type is article)") \
        == "works where country is not FR and type is not article"


# --- predicate negation (Change B is PARKED) stays valid -------------------- #

def test_predicate_negation_unchanged():
    # `is not` / `does not contain` are operators, not the bare keyword — untouched.
    parse("works where country is not FR")
    parse("works where title does not contain dog")
    parse("works where it's not open access")  # boolean flip


# --- no nested parens: `not(group) and x` ----------------------------------- #

def test_not_group_and_x_has_no_nested_parens():
    # The function-call parens ARE the grouping, so there is never a `(not (…))`.
    out = _identity("works where title contains (not(dog or cat) and wombat)")
    assert "(not (" not in out and "not ((" not in out
    # canonical NNF: not(dog or cat) -> not(dog) and not(cat), flattened into the AND
    assert out == "works where title contains (not(cat) and not(dog) and wombat)"
