"""
oql_render v2 — an OQO-faithful, layout-bearing render tree for the no-code
builder + the #463 view-code dialog (oxjob #428).

WHY THIS EXISTS
---------------
The v1 `oql_render` tree (oql_render_tree.py) FACTORS a same-column boolean into
one `ClauseNode` whose value-internal structure is flattened into literal `(` /
` or ` / `)` *text segments*. That is fine for stringifying to OQL, but it hides
the tree the OQO actually is: `title contains (Boy or Girl)` is, in OQO, a
`BranchFilter(or, [Leaf(title,"Boy"), Leaf(title,"Girl")])` — a real tree down to
scalar leaves (`LeafFilter.value` is a bare scalar; it *cannot* hold a list).

v2 mirrors that OQO tree structurally — value sub-clauses are real nodes
(`vgroup`/`vleaf`) — and carries the canonical LAYOUT (line breaks + indent) on
the tree so the client never re-derives the formatting rules. Both the builder's
visual rows and #463's OQL text pane render from the SAME `lines` projection, so
their line-number gutters cannot drift from the canonicalizer.

LAYOUT MODEL (oxjob #428, decided with Jason: "match line-for-line with OQL")
-----------------------------------------------------------------------------
The builder's `lines` MUST match the canonical OQL pane (`format_oql`) line for
line — same breaks, same indentation, same content per line — so the no-code
builder and the OQL text read identically. Rather than maintain a second layout
engine that has to stay byte-identical to `format_oql` forever, we use
`format_oql` as the SINGLE layout engine and REFLOW the v2 token stream onto its
lines:

  1. emit the v2 tree's tokens INLINE, in order (each carries its node id + the
     metadata the client needs: value / entity / negated / column_id);
  2. run `format_oql` to get the canonical multi-line string;
  3. walk that string and assign each token to the line its characters land on.

This is correct by construction: `format_oql` only ever reformats WHITESPACE
(line breaks + indentation; it never reorders or rewrites non-whitespace
characters), so the non-whitespace character sequence of the canonical string is
identical to the concatenated inline tokens. Every token's non-whitespace
characters therefore fall on exactly one line, and the mapping is unambiguous.
A corpus-wide contract test asserts `lines == format_oql` for every valid query.

Because the layout is now width-based (not structural), two structurally-identical
clauses can lay out differently when one is longer — that is intentional: it is
what the OQL pane does.

INVARIANT: joining `lines` (indent + token text) re-parses to the same OQO as the
canonical `oql` — verified in the offline tests.
"""

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType
from query_translation.oql_lang import (
    _merge_same_field_items, _uniform_search_base, _uniform_eq_column,
    _oql_field, _render_term, _value_segments, _is_search_leaf, _leaf_node,
    _BY_COLUMN, _build_tree, format_oql,
)
from query_translation.oql_render_tree import _stringify_directive

class _IdGen:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"n{self.n}"


# ---------------------------------------------------------------------------
# OQO -> v2 node tree (dicts). Mirrors _filter_node's factoring decisions but
# emits value sub-trees as real nodes instead of flat text segments.
# ---------------------------------------------------------------------------

def _value_node(f: FilterType, render_leaf, idg) -> dict:
    """A factored value as a real tree: vleaf (scalar atom, +negation bit) or
    vgroup (parenthesized boolean of value nodes)."""
    if isinstance(f, LeafFilter):
        segs = render_leaf(f)
        display = "".join(s.text for s in segs)
        node = {"node": "vleaf", "id": idg(), "value": f.value,
                "display": display, "negated": bool(f.is_negated)}
        ent = next((s.meta for s in segs
                    if s.meta and s.meta.entity_id), None)
        if ent is not None:
            node["entity"] = {"id": ent.entity_id,
                              "short_id": ent.entity_short_id,
                              "display_name": ent.entity_display_name}
        return node
    children = [_value_node(c, render_leaf, idg) for c in f.filters]
    return {"node": "vgroup", "id": idg(), "join": f.join, "children": children}


def _expr_node(f: FilterType, top: bool, resolver, idg) -> dict:
    """OQO filter -> v2 expr node (clause | group), mirroring _filter_node."""
    if isinstance(f, BranchFilter) and f.is_negated:
        inner = _expr_node(BranchFilter(f.join, f.filters), False, resolver, idg)
        return {"node": "group", "id": idg(), "join": f.join, "negated": True,
                "paren": True, "children": [inner]}

    if isinstance(f, BranchFilter):
        scol = _uniform_search_base(f)
        if scol is not None:
            name, _ = _oql_field(scol)
            val = _value_node(
                f, lambda lf: [_seg_val(_render_term(lf.value, lf.column_id),
                                        lf.value)], idg)
            return {"node": "clause", "id": idg(), "clause_kind": "text",
                    "column_id": scol, "column": name, "operator": "contains",
                    "value": val}
        ecol = _uniform_eq_column(f)
        if ecol is not None:
            fld = _BY_COLUMN.get(ecol)
            name = fld.oql if fld else ecol
            val = _value_node(
                f, lambda lf: _value_segments(fld, lf.value, lf.column_id,
                                              resolver)[0], idg)
            kind = "entity" if (fld and fld.kind == "id") else "other"
            return {"node": "clause", "id": idg(), "clause_kind": kind,
                    "column_id": ecol, "column": name, "operator": "is",
                    "value": val}
        # generic boolean group of (possibly mixed-column) children
        items = _merge_same_field_items(list(f.filters), f.join)
        children = [_expr_node(c, False, resolver, idg) for c in items]
        if len(children) == 1:
            return children[0]
        return {"node": "group", "id": idg(), "join": f.join, "negated": False,
                "paren": not top, "children": children}

    # LeafFilter -> a simple clause (single value / bool phrase / null / comparison
    # / collection). Reuse _leaf_node for the display segments. `leaf` carries the
    # raw OQO leaf so the client can reconstruct the OQO from the v2 tree alone
    # (the tree is the edit model — oxjob #428 iter 22, decision B). Factored
    # clauses don't need `leaf`: their value vtree fully describes the branch.
    cn = _leaf_node(f, resolver)
    return {"node": "clause", "id": idg(), "clause_kind": cn.clause_kind,
            "column_id": cn.meta.column_id, "column": cn.meta.column_display_name,
            "operator": cn.meta.operator,
            "segments": [s.to_dict() for s in cn.segments],
            "leaf": f.to_dict()}


def _seg_val(text, value):
    from query_translation.oql_lang import _seg
    return _seg("value", text, value=value)


def build_tree(oqo: OQO, resolver=None) -> dict:
    """OQO -> v2 node tree (entity / where / directives), no layout yet."""
    idg = _IdGen()
    head = {"id": oqo.get_rows, "text": oqo.get_rows.lower()}
    where = None
    if oqo.filter_rows:
        rows = _merge_same_field_items(oqo.filter_rows, "and")
        if len(rows) == 1:
            where = _expr_node(rows[0], True, resolver, idg)
        else:
            children = [_expr_node(f, False, resolver, idg) for f in rows]
            where = {"node": "group", "id": idg(), "join": "and",
                     "negated": False, "paren": False, "implicit": True,
                     "children": children}
    # Directives reuse the v1 stringifier (they are always single-line).
    v1 = _build_tree(oqo, resolver)
    directives = [{"type": d.type, "text": _stringify_directive(d),
                   "meta": d.meta.to_dict()} for d in v1.directives]
    return {"version": "2.0", "entity": head,
            "where_keyword": " where " if where else "", "where": where,
            "directives": directives}


# ---------------------------------------------------------------------------
# Inline token stream: the v2 tree -> a flat, ordered list of tokens whose
# concatenated `text` IS the canonical one-line OQL (== render(oqo)). Each token
# carries its node `id` + the metadata the client needs. Token kinds:
#   kw     keyword chrome (works / where / not / sort by …) — inert
#   col    column chip            op   operator chip
#   paren  '(' or ')'             conn ' and ' / ' or ' connector
#   vbrick a value atom (chip / input); carries id, value, negated, entity?
#   text   raw passthrough (rare)
# These are reflowed onto `format_oql`'s lines by `_reflow` below.
# ---------------------------------------------------------------------------

_SEG2TOK = {"column": "col", "operator": "op", "value": "vbrick",
            "keyword": "kw", "id": "id", "text": "text"}


def _flat_tokens(tree: dict) -> list:
    toks = []

    def fv(v):
        if v["node"] == "vleaf":
            # `text` is stringify-canonical (incl. the bare `not ` prefix,
            # decision 23); the client renders `not` as chrome off `negated` and
            # shows `display` (the bare value) in the brick.
            text = f"not {v['display']}" if v["negated"] else v["display"]
            tok = {"t": "vbrick", "id": v["id"], "text": text,
                   "display": v["display"], "value": v["value"],
                   "negated": v["negated"]}
            if "entity" in v:
                tok["entity"] = v["entity"]
            toks.append(tok)
            return
        toks.append({"t": "paren", "id": v["id"], "text": "("})
        for i, c in enumerate(v["children"]):
            if i:
                toks.append({"t": "conn", "id": v["id"],
                             "text": f" {v['join']} ", "label": v["join"]})
            fv(c)
        toks.append({"t": "paren", "id": v["id"], "text": ")"})

    def fe(n):
        # A negated group renders as `not <child>` (decision 23, NNF): no parens
        # of its own — the single inner node supplies any it needs. This also
        # carries the `not` the old structural layout silently dropped.
        if n["node"] == "group" and n.get("negated"):
            toks.append({"t": "kw", "id": n["id"], "text": "not ", "label": "not"})
            for c in n["children"]:
                fe(c)
            return
        if n["node"] == "clause":
            v = n.get("value")
            if v is None:  # simple clause: its display segments verbatim
                for s in n["segments"]:
                    tok = {"t": _SEG2TOK.get(s["kind"], "text"), "id": n["id"],
                           "text": s["text"]}
                    m = s.get("meta") or {}
                    if "column_id" in m:
                        tok["column_id"] = m["column_id"]
                    if "value" in m:
                        tok["value"] = m["value"]
                    toks.append(tok)
                return
            toks.append({"t": "col", "id": n["id"], "text": n["column"],
                         "column_id": n["column_id"]})
            toks.append({"t": "op", "id": n["id"], "text": f" {n['operator']} "})
            fv(v)
            return
        # plain group: parens iff `paren`; children joined by the connector.
        paren = n.get("paren")
        if paren:
            toks.append({"t": "paren", "id": n["id"], "text": "("})
        for i, c in enumerate(n["children"]):
            if i:
                toks.append({"t": "conn", "id": n["id"],
                             "text": f" {n['join']} ", "label": n["join"]})
            fe(c)
        if paren:
            toks.append({"t": "paren", "id": n["id"], "text": ")"})

    toks.append({"t": "kw", "id": tree["entity"]["id"],
                 "text": tree["entity"]["text"], "label": tree["entity"]["text"]})
    where = tree.get("where")
    if where is not None:
        toks.append({"t": "kw", "text": tree["where_keyword"], "label": "where"})
        fe(where)
    for d in tree["directives"]:
        # leading space mirrors stringify (` sort by …`); on its own line the
        # space is harmless, inline it separates the directive from the clause.
        toks.append({"t": "kw", "text": " " + d["text"], "label": d["text"]})
    return toks


# ---------------------------------------------------------------------------
# Reflow: map the inline token stream onto `format_oql`'s exact lines. Correct
# by construction — `format_oql` only reformats WHITESPACE, so the canonical
# string and the concatenated tokens share an identical non-whitespace character
# sequence; each token's non-ws chars therefore land on exactly one line.
# ---------------------------------------------------------------------------

def _reflow(toks: list, canonical: str) -> list:
    nonws = []                      # token index for each non-ws char of `toks`
    for idx, t in enumerate(toks):
        for ch in t["text"]:
            if not ch.isspace():
                nonws.append(idx)
    lines, cur = [], {"indent": 0, "tokens": [], "_seen": set()}

    def flush():
        nonlocal cur
        if cur["tokens"]:
            lines.append({"indent": cur["indent"], "tokens": cur["tokens"]})
        cur = {"indent": 0, "tokens": [], "_seen": set()}

    ci, i, n = 0, 0, len(canonical)
    while i < n:
        ch = canonical[i]
        if ch == "\n":
            flush()
            j, ind = i + 1, 0
            while j < n and canonical[j] == " ":
                ind, j = ind + 1, j + 1
            cur["indent"], i = ind, j
            continue
        if ch.isspace():
            i += 1
            continue
        tk = nonws[ci]
        ci += 1
        if tk not in cur["_seen"]:
            cur["tokens"].append(toks[tk])
            cur["_seen"].add(tk)
        i += 1
    flush()
    for k, ln in enumerate(lines, 1):
        ln["n"] = k
    return lines


def layout(tree: dict, canonical: str):
    """Reflow the v2 tree's inline tokens onto the canonical `format_oql` lines."""
    return _reflow(_flat_tokens(tree), canonical)


def render_v2(oqo: OQO, resolver=None) -> dict:
    tree = build_tree(oqo, resolver)
    canonical = format_oql(_build_tree(oqo, resolver))
    tree["lines"] = layout(tree, canonical)
    return tree


def lines_to_text(lines) -> str:
    """Stringify the `lines` projection back to multi-line OQL. Used by tests to
    assert it round-trips to the same OQO, and (ws-normalized) equals the
    canonical `format_oql` line for line."""
    out = []
    for ln in lines:
        out.append(" " * ln["indent"] + "".join(t["text"] for t in ln["tokens"]))
    return "\n".join(out)
