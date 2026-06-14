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

LAYOUT MODEL (oxjob #428 iter 22, decided with Jason)
-----------------------------------------------------
LOGICAL lines, not width-wrapped. A node "explodes" onto its own lines IFF it
contains a nested parenthesized sub-group; a flat boolean list stays on ONE
logical line and SOFT-wraps in the UI (chips by pixel, text by CSS). This is a
*structural* rule (independent of the 80-col `format_oql` used for the canonical
`oql` string), so two structurally-identical clauses always lay out identically.

Top-level `where` filter rows are each their own line (the builder's rows): the
first rides the `works where …` line, the rest start new lines led by `and`/`or`.

INVARIANT: joining `lines` (indent + token text, structural newlines only)
re-parses to the same OQO as the canonical `oql` — verified in the offline tests.
"""

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType
from query_translation.oql_lang import (
    _merge_same_field_items, _uniform_search_base, _uniform_eq_column,
    _oql_field, _render_term, _value_segments, _is_search_leaf, _leaf_node,
    _BY_COLUMN, _build_tree,
)
from query_translation.oql_render_tree import _stringify_directive

_INDENT = 2  # spaces per nesting level (matches format_oql)


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

    # LeafFilter -> a simple clause. Reuse _leaf_node for the display segments,
    # and represent its value as a single vleaf when there is a discrete value.
    cn = _leaf_node(f, resolver)
    node = {"node": "clause", "id": idg(), "clause_kind": cn.clause_kind,
            "column_id": cn.meta.column_id, "column": cn.meta.column_display_name,
            "operator": cn.meta.operator,
            "segments": [s.to_dict() for s in cn.segments]}
    return node


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
# Block (explode) decision: a node renders multi-line IFF it contains a nested
# parenthesized sub-group. Flat boolean lists stay one (soft-wrapping) line.
# ---------------------------------------------------------------------------

def _vnode_block(v: dict) -> bool:
    if v["node"] == "vleaf":
        return False
    return any(c["node"] == "vgroup" for c in v["children"])


def _expr_block(n: dict) -> bool:
    if n["node"] == "clause":
        v = n.get("value")
        return bool(v) and v["node"] == "vgroup" and _vnode_block(v)
    # group: explodes if it holds a nested group, or a block clause
    return any(c["node"] == "group" or _expr_block(c) for c in n["children"])


# ---------------------------------------------------------------------------
# Layout: v2 tree -> ordered logical `lines`. Each line = {n, indent, tokens}.
# A token is {t, text, id?, ...meta}. Token kinds:
#   kw     keyword chrome (works / where / sort by …) — inert
#   col    column chip            op   operator chip
#   paren  '(' or ')'             conn ' and ' / ' or ' connector
#   vbrick a value atom (chip / input); carries id, value, negated, entity?
#   text   raw passthrough (rare)
# `id` ties a token to its v2 node so the client can route edits.
# ---------------------------------------------------------------------------

def layout(tree: dict):
    lines = []
    cur = {"indent": 0, "tokens": []}

    def flush():
        nonlocal cur
        if cur["tokens"]:
            lines.append(cur)
        cur = {"indent": 0, "tokens": []}

    def newline(indent):
        nonlocal cur
        flush()
        cur = {"indent": indent, "tokens": []}

    def emit(tok):
        cur["tokens"].append(tok)

    # --- value tree ---------------------------------------------------------
    def lay_value(v, indent):
        if v["node"] == "vleaf":
            # token `text` is stringify-canonical (incl. the bare `not ` prefix,
            # decision 23); the client renders `not` as chrome off the `negated`
            # flag and shows `display` (the bare value) in the brick.
            text = f"not {v['display']}" if v["negated"] else v["display"]
            tok = {"t": "vbrick", "id": v["id"], "text": text,
                   "display": v["display"], "value": v["value"],
                   "negated": v["negated"]}
            if "entity" in v:
                tok["entity"] = v["entity"]
            emit(tok)
            return
        # vgroup
        children = v["children"]
        if not _vnode_block(v):  # flat -> inline (a or b or c)
            for i, c in enumerate(children):
                if i:
                    emit({"t": "conn", "id": v["id"], "text": f" {v['join']} ",
                          "label": v["join"]})
                lay_value(c, indent)
            return
        # block -> each child on its own line(s), LEADING connectors (the SQL
        # "leading AND" convention — same rule as top-level rows: first child
        # has no connector, every continuation row starts with `and `/`or `).
        for i, c in enumerate(children):
            newline(indent)
            if i:
                emit({"t": "conn", "id": v["id"], "text": f"{v['join']} ",
                      "label": v["join"]})
            if c["node"] == "vgroup":
                emit({"t": "paren", "id": c["id"], "text": "("})
                lay_value(c, indent + _INDENT)
                emit({"t": "paren", "id": c["id"], "text": ")"})
            else:
                lay_value(c, indent)

    # --- expr (clause | group) ---------------------------------------------
    _SEG2TOK = {"column": "col", "operator": "op", "value": "vbrick",
                "keyword": "kw", "id": "id", "text": "text"}

    def lay_clause(n, indent):
        v = n.get("value")
        if v is None:  # simple clause: render its display segments verbatim
            for s in n["segments"]:
                tok = {"t": _SEG2TOK.get(s["kind"], "text"), "id": n["id"],
                       "text": s["text"]}
                m = s.get("meta") or {}
                if "column_id" in m:
                    tok["column_id"] = m["column_id"]
                if "value" in m:
                    tok["value"] = m["value"]
                emit(tok)
            return
        emit({"t": "col", "id": n["id"], "text": n["column"],
              "column_id": n["column_id"]})
        emit({"t": "op", "id": n["id"], "text": f" {n['operator']} "})
        block = v["node"] == "vgroup" and _vnode_block(v)
        emit({"t": "paren", "id": v["id"], "text": "("})
        if block:
            lay_value(v, indent + _INDENT)
            newline(indent)
            emit({"t": "paren", "id": v["id"], "text": ")"})
        else:
            lay_value(v, indent)
            emit({"t": "paren", "id": v["id"], "text": ")"})

    def lay_group_paren(n, indent):
        """A parenthesized clause-level group (e.g. (type is x or type is y))."""
        block = _expr_block(n)
        emit({"t": "paren", "id": n["id"], "text": "("})
        if not block:
            for i, c in enumerate(n["children"]):
                if i:
                    emit({"t": "conn", "id": n["id"], "text": f" {n['join']} ",
                          "label": n["join"]})
                lay_expr_inline(c, indent)
            emit({"t": "paren", "id": n["id"], "text": ")"})
        else:
            for i, c in enumerate(n["children"]):
                newline(indent + _INDENT)
                if i:
                    emit({"t": "conn", "id": n["id"], "text": f"{n['join']} ",
                          "label": n["join"]})
                lay_expr(c, indent + _INDENT)
            newline(indent)
            emit({"t": "paren", "id": n["id"], "text": ")"})

    def lay_expr_inline(n, indent):
        if n["node"] == "clause":
            lay_clause(n, indent)
        else:
            lay_group_paren(n, indent)

    def lay_expr(n, indent):
        if n["node"] == "clause":
            lay_clause(n, indent)
        else:
            lay_group_paren(n, indent)

    # --- top level ----------------------------------------------------------
    emit({"t": "kw", "id": tree["entity"]["id"], "text": tree["entity"]["text"],
          "label": tree["entity"]["text"]})
    where = tree.get("where")
    if where is not None:
        emit({"t": "kw", "text": tree["where_keyword"], "label": "where"})
        if where["node"] == "group" and where.get("implicit"):
            # top-level filter rows: first rides this line, rest are new lines
            for i, c in enumerate(where["children"]):
                if i:
                    newline(_INDENT)
                    emit({"t": "conn", "id": where["id"],
                          "text": f"{where['join']} ", "label": where["join"]})
                lay_expr(c, _INDENT)
        else:
            lay_expr(where, _INDENT)
    for d in tree["directives"]:
        newline(0)
        emit({"t": "kw", "text": d["text"], "label": d["text"]})
    flush()
    for i, ln in enumerate(lines, 1):
        ln["n"] = i
    return lines


def render_v2(oqo: OQO, resolver=None) -> dict:
    tree = build_tree(oqo, resolver)
    tree["lines"] = layout(tree)
    return tree


def lines_to_text(lines) -> str:
    """Stringify the `lines` projection to logical-line OQL (structural newlines
    only; long value lists stay on one line). Used by tests to assert the layout
    round-trips to the same OQO as the canonical string."""
    out = []
    for ln in lines:
        out.append(" " * ln["indent"] + "".join(t["text"] for t in ln["tokens"]))
    return "\n".join(out)
