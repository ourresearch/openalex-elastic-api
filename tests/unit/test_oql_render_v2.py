"""
Tests for oql_render v2 (oxjob #428 iter 22) — the OQO-faithful, layout-bearing
render used by the no-code builder + #463 view-code dialog.

Invariants:
- LAYOUT round-trip: joining the `lines` projection re-parses to the SAME OQO as
  the canonical render (so the builder's rows can't drift from the language).
- IDEMPOTENCE: laying out the round-tripped query yields identical lines.
- LINE-FOR-LINE with `format_oql`: the builder's `lines` reproduce the canonical
  OQL pane exactly (same breaks, same indentation, same content per line), so the
  no-code builder and the OQL text read identically (oxjob #428, Jason's ask).
  Layout is width-based — `render_v2` reflows the token stream onto `format_oql`'s
  own lines (the single layout engine), so the two cannot diverge.
"""

import pathlib

import pytest
import yaml
from query_translation.oqo import OQO, LeafFilter, BranchFilter
from query_translation.oql_lang import parse, render, render_tree, format_oql
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


def _norm(text):
    """Lines with whitespace collapsed — token-edge spaces (e.g. a leading-space
    ` or ` connector chip) are invisible in the builder, so layout equality is
    asserted up to whitespace runs."""
    return [" ".join(line.split()) for line in text.splitlines()]


def _fo(oql):
    """The canonical OQL pane string the builder must match line-for-line."""
    return format_oql(render_tree(parse(oql))[1])


def _v2_text(oql):
    return lines_to_text(render_v2(parse(oql))["lines"])


def test_short_query_stays_one_line():
    """A query whose one-line form fits the width is a single line — same as the
    OQL pane (no gratuitous explosion)."""
    oql = "works where title contains ((a or b) and (c or d))"
    assert _norm(_v2_text(oql)) == ["works where title contains ((a or b) and (c or d))"]
    assert _norm(_v2_text(oql)) == _norm(_fo(oql))


def test_clause_group_and_nested_value_list_explode_like_oql():
    """The SR-style query Jason flagged: an over-width parenthesized clause group
    explodes (open paren / clauses indented / close paren), AND the long value
    list inside `title/abstract contains (…)` ALSO explodes one-value-per-line —
    line-for-line with the OQL pane (the value list no longer stays inline)."""
    oql = ('works where (keyword is types/article or title/abstract contains '
           '(INR or aPTT or coagulopathy or thrombocytopenia or '
           '"blood coagulation disorders" or "coagulation disorder")) '
           'and language is en')
    assert _norm(_v2_text(oql)) == _norm(_fo(oql))
    # spot-check the shape Jason wanted: clause line ends with the open paren,
    # values start indented on the next lines.
    norm = _norm(_v2_text(oql))
    assert norm[0] == "works where ("
    assert "or title/abstract contains (" in norm
    assert "INR" in norm                           # first value, bare on its line
    assert "or aPTT" in norm                        # later value, connective leads


def test_long_flat_value_list_explodes_by_width():
    """A long flat OR list now explodes by width (matching the OQL pane) instead
    of staying on one soft-wrapping line — the reversed behavior Jason asked for."""
    long_or = " or ".join(f"term{i}" for i in range(40))
    oql = f"works where title contains ({long_or})"
    assert len(render_v2(parse(oql))["lines"]) > 1
    assert _norm(_v2_text(oql)) == _norm(_fo(oql))


def test_works_where_merged_on_one_line():
    """Entity + where + first clause share line 1 (builder no longer splits
    `works` onto its own row)."""
    lines = _texts(_lines("works where title contains bikes"))
    assert lines == ["works where title contains bikes"]


def test_example_78_matches_oql_pane():
    """The real SR query (zd#8101): title's nested sub-groups explode, the short
    full-text flat list stays inline, title/abstract explodes — all line-for-line
    with the OQL pane."""
    oql = (
        "works where title contains ("
        "(Boy or Girl or Minors or adolescent or boys) and "
        "(Height or bodyweight or fat or obese or weight)) "
        "and full text contains (Britain or England or GB or UK or Wales) "
        "and title/abstract contains ((attitude or beliefs or diaries) and "
        "(interview or interviews or perceptions))")
    norm = _norm(_v2_text(oql))
    assert norm == _norm(_fo(oql))
    assert norm[0] == "works where title contains ("
    assert "(Boy or Girl or Minors or adolescent or boys)" in norm
    assert "and (Height or bodyweight or fat or obese or weight)" in norm
    assert "and full text contains (Britain or England or GB or UK or Wales)" in norm


# --- the contract: the builder's lines ARE the OQL pane, line for line --------

_CONTRACT_CASES = [
    "works where title contains bikes",                       # one line
    "works where type is article and is_oa is true",          # short, one line
    "works where (type is article or type is book) and title contains cats",
    "works where institution is (I136199984 or I27837315) "
        "and title contains (not bikes and cars)",
    "works where title contains (a or (b and c) or (d and (e or f)))",
    # long clause group + long value list -> both explode (Jason's SR case)
    'works where (keyword is types/article or title/abstract contains '
        '(INR or aPTT or coagulopathy or thrombocytopenia or '
        '"blood coagulation disorders" or "coagulation disorder")) '
        'and (keyword is types/book or title/abstract contains '
        '(CVC or "central line" or "central venous catheter"))',
    # >8 items -> fill/pack mode
    "works where institution is (" + " or ".join(f"I{i}" for i in range(1, 40)) + ")",
    "works where not (type is article or type is book) and title contains x",
    "works where title contains bikes sort by cited_by_count desc",
]


@pytest.mark.parametrize("oql", _CONTRACT_CASES)
def test_lines_match_format_oql(oql):
    """Joining `lines` (ws-normalized) equals the canonical OQL pane line-for-line.
    This is THE contract: builder rows and OQL text cannot drift."""
    assert _norm(_v2_text(oql)) == _norm(_fo(oql))


def _corpus_oqls():
    path = pathlib.Path(__file__).resolve().parents[2] / "docs/oql/corpus.yaml"
    rows = yaml.safe_load(path.read_text())["rows"]
    out = []
    for r in rows:
        oql = r.get("oql")
        if not oql:
            continue
        try:
            parse(oql)            # skip the intentionally-invalid diagnostic rows
        except Exception:
            continue
        out.append(pytest.param(oql, id=str(r.get("id"))))
    return out


@pytest.mark.parametrize("oql", _corpus_oqls())
def test_corpus_lines_match_format_oql(oql):
    """Every VALID corpus query lays out line-for-line identically to the OQL
    pane — the strongest guarantee the two engines can't diverge."""
    assert _norm(_v2_text(oql)) == _norm(_fo(oql))


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


def _toks(oql):
    return [t for ln in render_v2(parse(oql))["lines"] for t in ln["tokens"]]


def test_single_negated_leaf_has_no_predicate_negation():
    """A single negated value renders `is` + a negated value brick, never the
    predicate `is not` (OQL has no predicate-level negation — decision 23). The
    canonical string is unchanged. (oxjob #428 non-mutating-predicate feedback.)"""
    toks = _toks("works where institution is not I97018004")
    op = next(t for t in toks if t["t"] == "op")
    assert op["text"] == " is "                       # not " is not "
    vb = next(t for t in toks if t["t"] == "vbrick")
    assert vb["negated"] is True
    assert vb["value"] == "I97018004"
    assert vb["display"] == "I97018004"               # bare; chip prepends the `not`
    # canonical char stream preserved -> round-trips + matches the OQL pane
    assert _norm(_v2_text("works where institution is not I97018004")) == \
        _norm(_fo("works where institution is not I97018004"))


def test_simple_value_carries_kind_hint():
    """The value brick of a simple clause carries the server's clause kind so the
    builder can render an entity chip even when the /properties catalog (keyed by
    group) can't resolve the column. (oxjob #428 bug 5: domain shown as an int.)"""
    toks = _toks("topics where domain is 3")
    vb = next(t for t in toks if t["t"] == "vbrick")
    assert vb["kind"] == "entity"


def test_boolean_phrase_is_an_interactive_value_brick():
    """A boolean clause renders its human phrase as an interactive value brick
    (toggleable), not inert keyword chrome. (oxjob #428 boolean-filter feedback.)"""
    toks = _toks("works where it's open access")
    phrase = next(t for t in toks if t.get("bool_phrase"))
    assert phrase["t"] == "vbrick"
    assert phrase["text"] == "it's open access"
    assert phrase["negated"] is False
    assert phrase["kind"] == "boolean"
    # negated bool -> the opposite phrase, still an interactive brick
    toks_n = _toks("works where it's not open access")
    phrase_n = next(t for t in toks_n if t.get("bool_phrase"))
    assert phrase_n["text"] == "it's not open access"
    assert phrase_n["negated"] is True
