"""
Tests for oql_render v2 (oxjob #428 iter 22) — the OQO-faithful, layout-bearing
render used by the no-code builder + #463 view-code dialog.

Invariants:
- LAYOUT round-trip: joining the `lines` projection re-parses to the SAME OQO as
  the canonical render (so the builder's rows can't drift from the language).
- IDEMPOTENCE: laying out the round-tripped query yields identical lines.
- STRUCTURAL line rule: a node explodes onto its own lines IFF it contains a
  nested parenthesized sub-group; flat boolean lists stay on one line —
  independent of length (unlike the 80-col `format_oql`).
"""

import pytest
from query_translation.oqo import OQO, LeafFilter, BranchFilter
from query_translation.oql_lang import parse, render
from query_translation.oql_render_v2 import render_v2, lines_to_text


# --- reference reconstruction: v2 tree -> OQO ------------------------------
# This is the algorithm the CLIENT will implement as v2ToOqo.js (oxjob #428
# iter 22, decision B: the v2 tree is the builder's edit model). Proving it
# here = proving the v2 tree is a COMPLETE, lossless edit model (the client can
# rebuild the OQO from the tree alone, with no side data). Mirrors the build
# direction in oql_render_v2._expr_node / _value_node.

def _value_to_filter(v, col, op):
    if v["node"] == "vleaf":
        return LeafFilter(column_id=col, value=v["value"], operator=op,
                          is_negated=v["negated"])
    return BranchFilter(join=v["join"],
                        filters=[_value_to_filter(c, col, op)
                                 for c in v["children"]])


def _expr_to_filter(n):
    if n["node"] == "clause":
        v = n.get("value")
        if v is not None:                       # factored: value vtree -> branch
            return _value_to_filter(v, n["column_id"], n["operator"])
        return LeafFilter.from_dict(n["leaf"])  # simple: raw leaf
    children = [_expr_to_filter(c) for c in n["children"]]
    if n.get("negated"):                        # NNF wrapper: not (group)
        inner = children[0]
        return BranchFilter(join=inner.join, filters=inner.filters,
                            is_negated=True)
    return BranchFilter(join=n["join"], filters=children)


def v2_tree_to_oqo(tree):
    oqo = OQO(get_rows=tree["entity"]["id"], filter_rows=[])
    w = tree.get("where")
    if w is not None:
        if w["node"] == "group" and w.get("implicit"):
            oqo.filter_rows = [_expr_to_filter(c) for c in w["children"]]
        else:
            oqo.filter_rows = [_expr_to_filter(w)]
    return oqo


def _lines(oql):
    return render_v2(parse(oql))["lines"]


def _texts(lines):
    return [" " * ln["indent"] + "".join(t["text"] for t in ln["tokens"])
            for ln in lines]


ROUND_TRIP_CASES = [
    "works where title contains bikes",
    "works where type is article and is_oa is true",
    "works where (type is article or type is book) and title contains cats",
    "works where title contains bikes sort by cited_by_count desc",
    "works where institution is (I136199984 or I27837315) "
        "and title contains (not bikes and cars)",
    "works where title contains (a or (b and c) or (d and (e or f)))",
    "works where publication_year >= 2019 and publication_year <= 2023",
    "works where title contains ((Boy or Girl or boys) and (Height or weight)) "
        "and full text contains (Britain or England or UK) "
        "and abstract contains ((attitude or beliefs) and (interview or surveys))",
]


@pytest.mark.parametrize("oql", ROUND_TRIP_CASES)
def test_layout_round_trips_to_same_oqo(oql):
    """Joining the lines projection re-parses to the same canonical OQO."""
    oqo = parse(oql)
    txt = lines_to_text(render_v2(oqo)["lines"])
    assert render(parse(txt)) == render(oqo)


@pytest.mark.parametrize("oql", ROUND_TRIP_CASES)
def test_v2_tree_is_a_complete_edit_model(oql):
    """The v2 tree alone reconstructs the SAME OQO (filter_rows) — proving the
    client can edit the tree and rebuild the query with no side data. This is
    the contract the client's v2ToOqo.js depends on."""
    oqo = parse(oql)
    tree = render_v2(oqo)
    rebuilt = v2_tree_to_oqo(tree)
    # compare the WHERE (filter) structure (sort/select stay component refs);
    # re-render both filter sets and compare canonical OQL of the filters.
    a = OQO(get_rows=oqo.get_rows, filter_rows=oqo.filter_rows)
    b = OQO(get_rows=rebuilt.get_rows, filter_rows=rebuilt.filter_rows)
    assert render(b) == render(a)


@pytest.mark.parametrize("oql", ROUND_TRIP_CASES)
def test_layout_is_idempotent(oql):
    """Laying out the round-tripped query yields identical lines."""
    v2 = render_v2(parse(oql))
    txt = lines_to_text(v2["lines"])
    assert render_v2(parse(txt))["lines"] == v2["lines"]


def test_flat_list_stays_one_line_regardless_of_length():
    """A long flat OR list is ONE logical line (soft-wraps in the UI), unlike
    the 80-col canonical string which hard-wraps it."""
    long_or = " or ".join(f"term{i}" for i in range(40))
    lines = _lines(f"works where title contains ({long_or})")
    assert len(lines) == 1


def test_group_with_subgroup_explodes_block_parens():
    """A value holding nested sub-groups explodes; each inner sub-group is a
    BLOCK — open paren alone, flat content on its own line, close paren alone —
    so every "(" starts a fresh line (issue A). Connectors TRAIL the preceding
    sub-group (`) and`), which is what keeps each open paren alone."""
    lines = _texts(_lines(
        "works where title contains ((a or b) and (c or d))"))
    assert lines == [
        "works where title contains (",
        "    (",
        "      a or b",
        "    ) and",
        "    (",
        "      c or d",
        "    )",
        "  )",
    ]


def test_mixed_column_clause_group_explodes_block():
    """A parenthesized MIXED-column clause group (e.g. `(keyword is X or
    title/abstract contains (...))`) is a block: open paren alone, each child
    clause indented on its own line led by the connector, close paren alone —
    matching the canonical OQL pane (oxjob #428: issue A extended from value
    sub-groups to clause groups). Previously these rendered all-inline with no
    indentation (the regression Jason hit on the SR-style query). The inner FLAT
    value list (`(INR or aPTT ...)`) stays inline — only the clause group breaks."""
    lines = _texts(_lines(
        "works where (type is types/article or title/abstract contains "
        "(INR or aPTT or coagulopathy)) and language is en"))
    assert lines == [
        "works where (",
        "    type is types/article",
        "    or title/abstract contains (INR or aPTT or coagulopathy)",
        "  )",
        "  and language is en",
    ]


def test_structurally_identical_clauses_lay_out_identically():
    """Two same-shape factored clauses explode the same way even when one is
    much longer (the consistency the width-based formatter lacks)."""
    short = "title contains ((a or b) and (c or d))"
    long = ("abstract contains ((" + " or ".join(f"x{i}" for i in range(30))
            + ") and (" + " or ".join(f"y{i}" for i in range(30)) + "))")
    lines = _texts(_lines(f"works where {short} and {long}"))
    # title clause: open / (block grp) / ) and / (block grp) / close  (lines 0-7)
    assert lines[0] == "works where title contains ("
    assert lines[1] == "    ("
    assert lines[3] == "    ) and"
    assert lines[7] == "  )"
    # abstract clause explodes identically (same 8-line block shape) even though
    # its value lists are far longer — flat content stays on ONE line (soft-wrap),
    # so the structure is width-INDEPENDENT.
    assert lines[8] == "  and abstract contains ("
    assert lines[9] == "    ("
    assert lines[11] == "    ) and"
    assert lines[15] == "  )"
    assert len(lines) == 16
    # the two clauses share the identical paren/connector skeleton (indents +
    # bracket lines), independent of how long their value lists are.
    assert [ln for ln in lines[1:8] if ln.strip() in ("(", ") and", ")")] == \
           [ln for ln in lines[9:16] if ln.strip() in ("(", ") and", ")")]


def test_works_where_merged_on_one_line():
    """Entity + where + first clause share line 1 (builder no longer splits
    `works` onto its own row)."""
    lines = _texts(_lines("works where title contains bikes"))
    assert lines == ["works where title contains bikes"]


def test_example_78_block_paren_logical_lines():
    """The real SR query (zd#8101): title explodes into block sub-groups, full
    text stays inline (flat list, one logical line + soft-wrap), title/abstract
    explodes — the builder renders these `lines` so its gutter matches the OQL
    pane line-for-line (issue A)."""
    oql = (
        "works where title contains ("
        "(Boy or Girl or Minors or adolescent or boys) and "
        "(Height or bodyweight or fat or obese or weight)) "
        "and full text contains (Britain or England or GB or UK or Wales) "
        "and title/abstract contains ((attitude or beliefs or diaries) and "
        "(interview or interviews or perceptions))")
    lines = _texts(_lines(oql))
    assert len(lines) == 17
    assert lines[0] == "works where title contains ("
    assert lines[1] == "    ("                                   # sub-group block open
    assert lines[3] == "    ) and"                               # trailing connector
    assert lines[7] == "  )"                                     # title clause close
    assert lines[8].startswith("  and full text contains (")     # inline (flat)
    assert lines[9] == "  and title/abstract contains ("         # explodes
    assert lines[16] == "  )"


def test_negated_value_round_trips_and_flags():
    """A negated value keeps `not` in the stringify text AND exposes a `negated`
    flag + bare display for the chip."""
    v2 = render_v2(parse("works where title contains (not bikes and cars)"))
    bricks = [t for ln in v2["lines"] for t in ln["tokens"]
              if t["t"] == "vbrick"]
    neg = next(b for b in bricks if b["value"] == "bikes")
    assert neg["negated"] is True
    assert neg["display"] == "bikes"
    assert neg["text"] == "not bikes"
