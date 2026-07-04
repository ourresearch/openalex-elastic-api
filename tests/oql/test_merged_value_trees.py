"""Decision 20 — canonical OQL merges same-field boolean structure into ONE
field-scoped value tree (the SR branch/leaf "One Right Way", #432/#363).

Published SRs are search-term trees, not filter-triple trees. The canonical
render therefore merges the children of one boolean node (incl. the implicit
top-level AND of filter_rows) that share a (field, base-operator) pair into a
single `field op (tree)` clause, with merged negated leaves rendered as a bare
`not <atom>` prefix inside the group (decision 23).
OQO is UNCHANGED (maximally distributed, NNF);
the parse direction already accepted every merged form, so this closes a
render/parse asymmetry. Spec §3.2.2; charter decision 20.

Run with:
    PYTHONPATH=. pytest tests/oql/test_merged_value_trees.py -q
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse, render_tree  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402


def _render(oql):
    return render_tree(canonicalize_oqo(parse(oql)), resolver=None)[0]


def _identity(oql):
    """render -> reparse -> render must be a fixed point AND OQO-identical."""
    canon = canonicalize_oqo(parse(oql))
    out = render_tree(canon, resolver=None)[0]
    canon2 = canonicalize_oqo(parse(out))
    assert canon.to_dict() == canon2.to_dict(), f"OQO identity broken for {oql!r}"
    out2 = render_tree(canon2, resolver=None)[0]
    assert out == out2, f"render not idempotent for {oql!r}"
    return out


# --- the merge: same-field structure renders as one clause ----------------- #

def test_sr_and_of_or_groups_merges_into_one_clause():
    assert _identity(
        "works where title has (vape or vaping) and title has (health or harm)"
    ) == "works where title has ((harm or health) and (vape or vaping))"


def test_positive_and_negated_leaf_merge_with_not_in_tree():
    assert _identity("works where title has cat and title does not have dog") \
        == "works where title has (not dog and cat)"


def test_demorganed_not_group_stays_in_one_clause():
    # `not (dog or bird)` -> NNF leaves -> merged back as in-tree bare nots
    assert _identity("works where title has (cat and not (dog or bird))") \
        == "works where title has (not bird and not dog and cat)"


def test_eq_columns_merge_too_all_filter_kinds():
    assert _identity("works where country is US and country is not FR") \
        == "works where country is (not FR and US)"


def test_is_not_group_renders_merged_not_two_clauses():
    assert _identity("works where country is not (US or FR)") \
        == "works where country is (not FR and not US)"


def test_search_leaf_merges_with_same_base_or_group():
    assert _identity(
        "works where title has health and title has (vape or vaping)"
    ) == "works where title has (health and (vape or vaping))"


def test_merge_anchors_at_first_same_field_row():
    # other-field rows keep their canonical position; same-field rows merge at
    # the first occurrence in canonical row order
    assert _identity(
        "works where title has alpha and country is US and title has beta"
    ) == "works where country is (US) and title has (alpha and beta)"


def test_stemmed_and_exact_share_one_merged_group():
    # base-field grouping: .search + .search.exact mix in one group (row-78 win)
    assert _identity(
        'works where title has "exact phrase" and title has (fuzzy words)'
    ) == 'works where title has (fuzzy words and "exact phrase")'


# --- what does NOT merge ---------------------------------------------------- #

def test_standalone_negated_leaf_renders_bare_prefix():
    # standalone negation renders as a bare `not` prefix INSIDE the value group (#554)
    assert _identity("works where title does not have dog") \
        == "works where title has (not dog)"
    assert _identity("works where country is not FR") \
        == "works where country is (not FR)"


def test_comparators_excluded_stay_separate_endpoint_clauses():
    # comparison operators never merge into a value tree; with the dash range
    # literal gone (decision 24) they stay as two endpoint clauses, lower first.
    assert _identity("works where year >= 2020 and year < 2024") \
        == "works where year >= (2020) and year < (2024)"


def test_lone_bounds_do_not_merge_into_a_value_tree():
    # two same-column bounds that do NOT form a closed range stay inequalities
    assert _identity("works where citation count > 100 and year >= 2020") \
        == "works where citation count > (100) and year >= (2020)"


def test_cross_field_stays_multi_clause():
    assert _identity("works where title has cat and abstract has dog") \
        == "works where abstract has (dog) and title has (cat)"


def test_mixed_field_or_branches_do_not_merge():
    # OR branches spanning different fields are not uniform -> no merge; the
    # body uses implicit-AND infix joins (decision 32 revert to infix parens).
    out = _identity(
        "works where (title has a or country is US) "
        "and (title has b or country is FR)"
    )
    assert out == (
        "works where (country is (FR) or title has (b))\n"
        "  and (country is (US) or title has (a))"
    )


# --- OQO is untouched (render-direction rule only) -------------------------- #

def test_merged_render_parses_back_to_distributed_oqo():
    fr = canonicalize_oqo(
        parse("works where title has (not dog and cat)")).to_dict()["filter_rows"]
    assert fr == [
        {"column_id": "display_name.search", "value": "dog",
         "operator": "has", "is_negated": True},
        {"column_id": "display_name.search", "value": "cat",
         "operator": "has"},
    ]


def test_hoisted_and_distributed_spellings_converge():
    a = canonicalize_oqo(parse(
        "works where title has ((vape or vaping) and (health or harm))"))
    b = canonicalize_oqo(parse(
        "works where title has (vape or vaping) and title has (health or harm)"))
    assert a.to_dict() == b.to_dict()


# --- formatter: long merged trees explode recursively ----------------------- #

def test_long_merged_clause_explodes_within_hard_ceiling():
    synonyms = " or ".join(f"term{i:02d}" for i in range(30))
    oql = (f"works where title has ({synonyms}) "
           f"and title has (health or harm or damage or risk)")
    out = _identity(oql)
    assert out.count("\n") > 2
    for line in out.split("\n"):
        if " or " in line or " and " in line:   # breakable lines obey the ceiling
            assert len(line) <= 100, f"breakable line exceeds 100 cols: {line!r}"
