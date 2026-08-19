"""Negated bare multi-word `.search.exact` values — the De Morgan split (oxjob #633 Cat 1).

A bare multi-word exact value is the no-stem AND-of-words; a NEGATED one is
NOT(a AND b). The polarity bit can't ride a split AND (NOT(a AND b) ≠
(NOT a AND NOT b)), so the canonical OQO is the De Morgan OR-branch of negated
per-token leaves — the shape the OQL door builds for
`has (not "a" or not "b")` / `does not have ("a" and "b")` (prod
count-verified: 321,820,019 = total − |a AND b| on
display_name.search.exact:cancer+treatment, 2026-08-19). Before this, the one
negated bare leaf mis-rendered in OQL as `has (not "cancer" and "treatment")`
— the `not` bound only the first token, a THIRD query.

The classic URL spelling of the OR-branch is the compact bang-prefixed run
`field:!cancer treatment` — never the pipe form `!a|!b`, whose leading `!`
re-parses as NOT(a OR b) (a different query again).

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_exact_negation_demorgan.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oqo import OQO, BranchFilter, LeafFilter  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.oql_lang import parse, render  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.url_renderer import (  # noqa: E402
    URLRenderError,
    render_filters,
    render_single_filter,
)

COL = "display_name.search.exact"


def _parse_filter(filter_string, entity_type="works"):
    return parse_url_to_oqo(entity_type, filter_string=filter_string)


def _negated_or_branch(oqo):
    rows = oqo.filter_rows
    assert len(rows) == 1 and isinstance(rows[0], BranchFilter), rows
    return rows[0]


# --- parse: the classic bang form De Morgans into the OR-branch ---------------

def test_negated_bare_multiword_parses_to_or_of_negated_leaves():
    oqo = _parse_filter("title.search.exact:!cancer treatment")
    branch = _negated_or_branch(oqo)
    assert branch.join == "or" and not branch.is_negated
    assert [(f.column_id, f.value, f.is_negated) for f in branch.filters] == [
        (COL, "cancer", True),
        (COL, "treatment", True),
    ]


def test_negated_single_token_stays_one_leaf():
    oqo = _parse_filter("title.search.exact:!cancer")
    (leaf,) = oqo.filter_rows
    assert isinstance(leaf, LeafFilter)
    assert (leaf.value, leaf.is_negated) == ("cancer", True)


def test_negated_quoted_phrase_stays_one_leaf():
    # A quoted phrase is a DIFFERENT query from the AND-of-words — its negation
    # keeps the single leaf and renders `not "…"` (faithful phrase negation).
    oqo = _parse_filter('title.search.exact:!"cancer treatment"')
    (leaf,) = oqo.filter_rows
    assert isinstance(leaf, LeafFilter)
    assert (leaf.value, leaf.is_negated) == ('"cancer treatment"', True)
    assert 'has (not "cancer treatment")' in render(oqo)


def test_negated_unsplittable_lucene_value_stays_one_leaf():
    # Category 2 (deferred): Lucene structure blocks the split — the leaf stays
    # bare-and-negated, faithful in OQO/URL.
    oqo = _parse_filter("title.search.exact:!+cancer treatment")
    (leaf,) = oqo.filter_rows
    assert isinstance(leaf, LeafFilter)
    assert (leaf.value, leaf.is_negated) == ("+cancer treatment", True)


def test_lifted_boolean_not_operand_demorgans():
    # A NOT operand inside a lifted Lucene boolean gets the same split:
    # `cancer AND NOT dark matter` → AND[cancer, OR[not dark, not matter]].
    oqo = _parse_filter("title.search.exact:cancer AND NOT dark matter")
    rows = oqo.filter_rows
    branches = [f for f in rows if isinstance(f, BranchFilter)]
    assert branches, rows
    inner = branches[-1]
    assert inner.join == "or"
    assert [(f.value, f.is_negated) for f in inner.filters] == [
        ("dark", True), ("matter", True)]


# --- OQL render: faithful `not "a" or not "b"`, never first-token-only not ----

def test_oql_render_is_faithful_de_morgan():
    oqo = _parse_filter("title.search.exact:!cancer treatment")
    oql = render(oqo)
    assert 'has (not "cancer" or not "treatment")' in oql
    assert 'not "cancer" and "treatment"' not in oql  # the old mis-negation


def test_oql_round_trips_to_fixed_point():
    oql_in = 'works where title has (not "cancer" or not "treatment")'
    oqo = parse(oql_in)
    assert render(oqo) == oql_in


def test_does_not_have_of_and_group_canonicalizes_to_same_form():
    a = canonicalize_oqo(parse('works where title does not have ("cancer" and "treatment")'))
    b = canonicalize_oqo(parse('works where title has (not "cancer" or not "treatment")'))
    assert a.to_dict() == b.to_dict()


# --- URL render: compact bang run, never a leading-! pipe list ----------------

def test_url_render_is_the_compact_bang_run_and_round_trips():
    oqo = _parse_filter("title.search.exact:!cancer treatment")
    rendered = render_filters(oqo.filter_rows)
    assert rendered == f"{COL}:!cancer treatment"
    assert "|" not in rendered
    back = _parse_filter(rendered)
    assert (canonicalize_oqo(back).to_dict()
            == canonicalize_oqo(oqo).to_dict())


def test_all_negated_or_branch_off_exact_has_no_url_form():
    # No compact spelling off `.search.exact` (a stemmed single negated leaf is
    # a different OQO shape) — refuse rather than emit the semantics-flipping
    # `!a|!b` pipe form.
    branch = BranchFilter(join="or", filters=[
        LeafFilter(column_id="display_name.search", value="cat",
                   operator="has", is_negated=True),
        LeafFilter(column_id="display_name.search", value="dog",
                   operator="has", is_negated=True),
    ])
    with pytest.raises(URLRenderError):
        render_single_filter(branch)


def test_mixed_polarity_or_branch_never_leads_with_bang():
    # `!book|article` would re-parse (and legacy-execute) as NOT(book OR article);
    # OR is commutative, so the positive member renders first.
    branch = BranchFilter(join="or", filters=[
        LeafFilter(column_id="type", value="book", operator="is", is_negated=True),
        LeafFilter(column_id="type", value="article", operator="is"),
    ])
    assert render_single_filter(branch) == "type:article|!book"


# --- canonicalizer: direct-OQO submissions converge on the same shape ---------

def test_canonicalizer_splits_negated_bare_leaf():
    raw = OQO(get_rows="works", filter_rows=[
        LeafFilter(column_id=COL, value="cancer treatment",
                   operator="has", is_negated=True)])
    branch = _negated_or_branch(canonicalize_oqo(raw))
    assert branch.join == "or"
    assert [(f.value, f.is_negated) for f in branch.filters] == [
        ("cancer", True), ("treatment", True)]


def test_canonicalizer_splits_positive_bare_leaf_into_sibling_rows():
    raw = OQO(get_rows="works", filter_rows=[
        LeafFilter(column_id=COL, value="cancer treatment", operator="has")])
    rows = canonicalize_oqo(raw).filter_rows
    assert [(f.value, f.is_negated) for f in rows] == [
        ("cancer", False), ("treatment", False)]


def test_render_of_uncanonicalized_negated_leaf_is_still_faithful():
    # Defense in depth: even a direct-OQO leaf that skipped canonicalization
    # must not render the first-token-only `not`.
    raw = OQO(get_rows="works", filter_rows=[
        LeafFilter(column_id=COL, value="cancer treatment",
                   operator="has", is_negated=True)])
    oql = render(raw, resolver=None)
    assert 'has (not "cancer" or not "treatment")' in oql
