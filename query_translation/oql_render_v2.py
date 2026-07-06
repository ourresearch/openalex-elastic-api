"""
oql_render v2 — an OQO-faithful, layout-bearing render tree for the no-code
builder + the #463 view-code dialog (oxjob #428).

WHY THIS EXISTS
---------------
The v1 `oql_render` tree (oql_render_tree.py) FACTORS a same-column boolean into
one `ClauseNode` whose value-internal structure is flattened into literal `(` /
` or ` / `)` *text segments*. That is fine for stringifying to OQL, but it hides
the tree the OQO actually is: `title has (Boy or Girl)` is, in OQO, a
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

from query_translation.oqo import OQO, BranchFilter
from query_translation.oql_lang import _build_tree, format_oql
from query_translation.oql_render_tree import GroupNode, _stringify_directive

class _IdGen:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"n{self.n}"


# ---------------------------------------------------------------------------
# v1 render tree -> v2 node tree (dicts). Since #566 this is a pure PROJECTION
# of the engine's ONE render walk (`oql_lang._build_tree`): factoring, merging,
# and negation decisions are made exactly once, in the engine, and read here
# structurally — factored clauses carry their value tree on `meta.vtree`,
# negation is `meta.negated` / vleaf `negated` / kind="negation" segments,
# and the OQO object each node renders rides `meta.oqo_ref` / the vtree's `_f`.
# Nothing in this module re-derives structure from OQO or from output text.
# ---------------------------------------------------------------------------

def _origin(origins, f, node):
    """Record id(OQO filter object) -> v2 node, for #474 addressing (errors[].path).
    No-op unless an `origins` dict is threaded through (default render path)."""
    if origins is not None and f is not None:
        origins[id(f)] = node
    return node


def _value_node(vt: dict, idg, origins=None) -> dict:
    """Project an engine value-tree node (oql_lang._build_value_tree) to the v2
    wire shape: strip the internal `_f`/`_segs` keys, stamp an id."""
    if vt["node"] == "vleaf":
        node = {"node": "vleaf", "id": idg(), "value": vt["value"],
                "display": vt["display"], "negated": vt["negated"]}
        if "entity" in vt:
            node["entity"] = vt["entity"]
        return _origin(origins, vt.get("_f"), node)
    children = [_value_node(c, idg, origins) for c in vt["children"]]
    node = {"node": "vgroup", "id": idg(), "join": vt["join"],
            "children": children}
    return _origin(origins, vt.get("_f"), node)


def _expr_node(n, top: bool, idg, origins=None) -> dict:
    """v1 ExprNode (ClauseNode | GroupNode) -> v2 expr node (clause | group)."""
    if isinstance(n, GroupNode):
        meta = n.meta
        if meta is not None and meta.negated:
            # `not (…)` wrapper: one inner child supplies its own parens.
            inner = _expr_node(n.children[0], False, idg, origins)
            return _origin(origins, meta.oqo_ref,
                           {"node": "group", "id": idg(), "join": n.join,
                            "negated": True, "paren": True,
                            "children": [inner]})
        children = [_expr_node(c, False, idg, origins) for c in n.children]
        node = {"node": "group", "id": idg(), "join": n.join,
                "negated": False, "paren": n.prefix == "(",
                "children": children}
        if meta is not None and meta.implicit:
            node["implicit"] = True
        return _origin(origins, meta.oqo_ref if meta else None, node)

    # ClauseNode. A factored clause carries its structural value tree.
    vt = n.meta.vtree
    if vt is not None:
        val = _value_node(vt, idg, origins)
        node = {"node": "clause", "id": idg(),
                "clause_kind": n.clause_kind, "column_id": n.meta.column_id,
                "operator": n.meta.operator, "value": val}
        # row-subject verb clause (#557): the canonical text is `it cites (…)`
        # — subject/verb come straight off the clause's own head segments
        # (`column`/`operator` kinds), so _flat_tokens matches format_oql;
        # `column` stays the BARE verb (the builder chip label).
        subj = next((s.text for s in n.segments if s.kind == "column"), None)
        verb = next((s.text for s in n.segments if s.kind == "operator"), None)
        if subj is not None and subj != n.meta.column_display_name:
            node.update({"column": n.meta.column_display_name,
                         "subject": subj, "verb": verb})
        else:
            node["column"] = n.meta.column_display_name
        return _origin(origins, n.meta.oqo_ref, node)

    # Simple clause (single value / bool phrase / null / comparison /
    # collection): the display segments ARE the model. `leaf` carries the raw
    # OQO leaf so the client can reconstruct the OQO from the v2 tree alone
    # (the tree is the edit model — oxjob #428 iter 22, decision B). Factored
    # clauses don't need `leaf`: their value vtree fully describes the branch.
    f = n.meta.oqo_ref
    return _origin(origins, f, {"node": "clause", "id": idg(),
            "clause_kind": n.clause_kind,
            "column_id": n.meta.column_id, "column": n.meta.column_display_name,
            "operator": n.meta.operator,
            "segments": [s.to_dict() for s in n.segments],
            "leaf": f.to_dict() if f is not None else None})


def build_tree(oqo: OQO, resolver=None, origins=None) -> dict:
    """OQO -> v2 node tree (entity / where / directives), no layout yet.

    `origins` (optional, #474): a dict populated with `id(OQO filter) -> v2 node`
    for every filter object reached, so addressing can map a validator's OQO-path
    diagnostic back to a decimal address. Default None keeps the render path inert."""
    return _build_tree_v2(oqo, resolver, origins)[0]


def _build_tree_v2(oqo: OQO, resolver=None, origins=None):
    """(v2 tree, v1 tree) — ONE engine walk (`_build_tree`) makes every
    factoring/negation decision; the v2 tree is projected from its output."""
    idg = _IdGen()
    v1 = _build_tree(oqo, resolver)
    head = {"id": oqo.get_rows, "text": oqo.get_rows.lower()}
    where = None
    if v1.where is not None:
        where = _expr_node(v1.where, True, idg, origins)
    directives = [{"type": d.type, "text": _stringify_directive(d),
                   "meta": d.meta.to_dict()} for d in v1.directives]
    return {"version": "2.0", "entity": head,
            # Corpus selector parenthetical (#481), e.g. " (all corpora)"; ""
            # for the default core corpus. Reuses the v1 tree's computed phrase.
            "corpus_phrase": v1.corpus_phrase,
            "where_keyword": " where " if where is not None else "",
            "where": where,
            "directives": directives}, v1


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
        # a value group renders as `(a or b)` / `(a and b)`: parens + an infix
        # `or`/`and` connector between children.
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
            if v is None:  # simple clause: render from its display segments
                leaf = n.get("leaf") or {}
                neg = bool(leaf.get("is_negated"))
                ck = n.get("clause_kind")
                for s in n["segments"]:
                    kind = s["kind"]
                    # #554: `_leaf_node` renders a negated entity/other `is` leaf
                    # as `is (` + a structural negation segment + value + `)`.
                    # The builder carries negation ON the value brick (below), so
                    # skip the standalone prefix — emitting both would double it.
                    # (#566: recognized by segment KIND, not by matching output
                    # text.)
                    if kind == "negation" and neg and ck in ("entity", "other"):
                        continue
                    tok = {"t": _SEG2TOK.get(kind, "text"), "id": n["id"],
                           "text": s["text"]}
                    m = s.get("meta") or {}
                    if "column_id" in m:
                        tok["column_id"] = m["column_id"]
                    if "value" in m:
                        tok["value"] = m["value"]
                    # A boolean clause is now a plain `<name> is (true|false)` (oxjob
                    # #363). Surface its true/false value segment as an interactive
                    # boolean-kind value brick the builder can toggle; negation is
                    # already folded into the value at render, so the brick is never
                    # negated and there is no separate `not`.
                    if ck == "boolean" and kind == "value":
                        tok["t"] = "vbrick"
                        tok["kind"] = "boolean"
                        tok["value"] = (s.get("meta") or {}).get("value")
                    # Predicate-level negation is not part of OQL (decision 23), and
                    # since #554 the canonical render already puts `not` inside the
                    # value group. Move it onto the VALUE brick so the builder shows
                    # `is` + `(` + a negated value chip + `)`, never inert-text `not`.
                    # The canonical character stream is unchanged (the skipped `not `
                    # segment above reappears as the brick's `not ` prefix).
                    if kind == "value" and neg and ck in ("entity", "other"):
                        tok["display"] = s["text"]        # bare value, no prefix
                        tok["text"] = "not " + s["text"]  # keeps the canonical stream
                        tok["negated"] = True
                    # Let the client trust the server's value KIND. The /properties
                    # catalog the builder consults is keyed by group, so a column like
                    # `domain.id` isn't found there and would fall back to a bare scalar
                    # brick; the kind hint makes it render an entity chip (oxjob #428 bug
                    # 5: "domain shown as an int").
                    if kind == "value" and "kind" not in tok:
                        tok["kind"] = ck
                    toks.append(tok)
                return
            if n.get("subject"):
                # row-subject verb clause (#557): `it` + ` cites ` / `'s cited
                # by ` … concatenates to the canonical text; the chip label is
                # n["column"] (the bare verb), same as the simple-leaf path.
                toks.append({"t": "col", "id": n["id"], "text": n["subject"],
                             "column_id": n["column_id"]})
                toks.append({"t": "op", "id": n["id"], "text": n["verb"]})
            else:
                toks.append({"t": "col", "id": n["id"], "text": n["column"],
                             "column_id": n["column_id"]})
                toks.append({"t": "op", "id": n["id"],
                             "text": f" {n['operator']} "})
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
    # Corpus selector parenthetical (#481), e.g. " (all corpora)". Emitted as its
    # own token after the entity so it lands on `format_oql`'s line for the head;
    # "" (core) contributes nothing. A distinct `t` so the GUI builder can target
    # it as the corpus chip later.
    corpus_phrase = tree.get("corpus_phrase") or ""
    if corpus_phrase:
        toks.append({"t": "corpus", "text": corpus_phrase,
                     "label": corpus_phrase.strip(" ()")})
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
    return render_v2_and_oql(oqo, resolver)[0]


def render_v2_and_oql(oqo: OQO, resolver=None):
    """(v2 render tree, canonical OQL string) from the ONE engine walk (#566)
    — the string is the same `format_oql` output the tree's `lines` were laid
    out from, so callers (views.render_all_formats) need no second render."""
    tree, v1 = _build_tree_v2(oqo, resolver)
    canonical = format_oql(v1)
    tree["lines"] = layout(tree, canonical)
    # #474: decimal addresses for the builder footer/gutter. Stamp every structural
    # node with `addr` (list of ints), then tag each rendered token with the address
    # of *what it is*, as a display-ready dotted string, so the client shows "the
    # address of whatever you're hovering" with no client-side derivation. Additive —
    # tokens whose node isn't addressed (entity / `where` chrome) have no `addr`.
    id_to_node = {n["id"]: n for n in stamp_addresses(tree).values()}
    for ln in tree["lines"]:
        for tok in ln["tokens"]:
            node = id_to_node.get(tok.get("id"))
            if node is None:
                continue
            addr = node["addr"]
            # A simple (non-factored) clause's scalar value is its `.1` child, but it
            # rides the clause node — so a value brick there addresses .1, while the
            # field/operator tokens address the clause. Factored values are their own
            # vleaf nodes (already value-level). A boolean's true/false brick is an
            # ordinary `.1` value too now (oxjob #363).
            if tok.get("t") == "vbrick" and node["node"] == "clause":
                addr = addr + [1]
            tok["addr"] = dotted(addr)
    return tree, canonical


def lines_to_text(lines) -> str:
    """Stringify the `lines` projection back to multi-line OQL. Used by tests to
    assert it round-trips to the same OQO, and (ws-normalized) equals the
    canonical `format_oql` line for line."""
    out = []
    for ln in lines:
        out.append(" " * ln["indent"] + "".join(t["text"] for t in ln["tokens"]))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Decimal addressing (oxjob #474). An outline coordinate for every meaningful
# node in the canonical OQL filter tree — `1`, `3.1`, `4.1.2` — for diagnostics
# (errors[].path), the builder gutter, and human reference. Spec + worked cases:
# docs/oql-addressing.md (the §8 cases are mirrored as `addr:` rows in
# docs/oql/corpus.yaml). It is a PURE walk of this v2 tree; it changes nothing.
#
# The rules, all grounded in "address what is a distinct token in the rendered
# OQL string" (so the address matches what the user reads):
#   * The whole `where` is one implicit ROOT group. Its head `0` is the root
#     conjunction (the top-level join); its clauses are `1, 2, 3…`. A single
#     top-level clause has no conjunction, so no `0` — it is just `1`.
#   * The ENTITY (`works`) is the query subject, not a filter node — unaddressed.
#   * `N.0` = a node's head: a group's join, a leaf's field.
#   * `N.1, N.2…` = children: a group's members, or a leaf's value(s). A leaf
#     whose value is a group FUSES — the group's operands become the leaf's
#     `.1, .2…` directly (the value-root join rides the leaf as an attribute, the
#     field already owning `.0`); a nested value group keeps its own `.0` join.
#   * A BOOLEAN flag is atomic — one fused phrase (`it's open access`) with no
#     separable field or value token, so just `N` (no `.0`, no `.1`). Its
#     true/false lives in the OQO, not the OQL string, so it gets no address.
#   * Internal address = list of ints (GraphQL errors[].path shape); display is
#     dotted, always, semver-style (`1.10` is the tenth child; dots delimit).
#   * parens, operators, and `not` (`is_negated`) are node ATTRIBUTES, not nodes.
# ---------------------------------------------------------------------------

def _addr_field_label(n: dict) -> str:
    return n.get("column")


def _addr_scalar_value(n: dict):
    """The displayed value token of a simple (non-factored) leaf, or None when
    there is none. A boolean is now `<name> is true|false`, so its true/false token
    is addressable like any other value (oxjob #363). Null renders `unknown`."""
    for s in n.get("segments", []):
        if s["kind"] == "value":
            return s["text"]
    return None


def _addr_vleaf_label(n: dict) -> str:
    return ("not " if n.get("negated") else "") + str(n.get("display"))


def address_index(tree: dict) -> list:
    """Walk the v2 render tree → an ordered list of address entries, the full
    logical numbering (the normative table in docs/oql-addressing.md §8).

    Each entry is `{"addr": [int, …], "kind": str, "label": str, "node": dict|None}`.
    `node` is the backing v2 dict when the address names a structural node
    (clause / group / vgroup / vleaf); it is None for positions that are tokens
    rather than nodes (the root conjunction, a leaf's field head, a group's join,
    a simple leaf's scalar value)."""
    out = []

    def emit(addr, kind, label, node=None):
        out.append({"addr": list(addr), "kind": kind, "label": label, "node": node})

    def walk_value(n, base):
        if n["node"] == "vleaf":
            emit(base, "value", _addr_vleaf_label(n), n)
            return
        emit(base, "vgroup", "( … )", n)              # nested value group
        emit(base + (0,), "join", n["join"])          # its head
        for i, c in enumerate(n["children"], 1):
            walk_value(c, base + (i,))

    def walk_expr(n, base):
        if n["node"] == "clause":
            # A boolean is an ordinary `<name> is true|false` clause now (oxjob
            # #363): field at .0, true/false value at .1 — same as any value clause.
            emit(base, "clause",
                 f"{n.get('column')} {n.get('operator') or ''}".strip(), n)
            emit(base + (0,), "field", _addr_field_label(n))
            v = n.get("value")
            if v is None:
                sv = _addr_scalar_value(n)
                if sv is not None:
                    emit(base + (1,), "value", sv)
            elif v["node"] == "vleaf":
                emit(base + (1,), "value", _addr_vleaf_label(v), v)
            else:                                      # value group fuses into leaf
                for i, c in enumerate(v["children"], 1):
                    walk_value(c, base + (i,))
            return
        # cross-field clause group
        emit(base, "group", "( … )", n)
        emit(base + (0,), "join", n["join"])
        for i, c in enumerate(n["children"], 1):
            walk_expr(c, base + (i,))

    where = tree.get("where")
    if where is None:
        return out
    if where["node"] == "group" and where.get("implicit"):
        emit((0,), "root-join", where["join"])        # the root conjunction
        for i, c in enumerate(where["children"], 1):
            walk_expr(c, (i,))
    else:
        walk_expr(where, (1,))                          # single top-level clause
    return out


def stamp_addresses(tree: dict) -> dict:
    """Stamp `node["addr"]` (an int list, alongside the opaque `id`) on every
    structural node and return the flat `{tuple(addr): node}` lookup map. Pure
    convenience over `address_index` for consumers that hold the tree."""
    index = {}
    for e in address_index(tree):
        if e["node"] is not None:
            e["node"]["addr"] = e["addr"]
            index[tuple(e["addr"])] = e["node"]
    return index


def dotted(addr) -> str:
    """Display form of an address: dotted, always (semver-style). `[1, 10]` -> `1.10`."""
    return ".".join(str(x) for x in addr)


# Trailing parts of a validator `location` that name a sub-attribute of a filter
# node (the node itself is what we address). `.filters` (empty_branch) and `.join`
# resolve to the branch node; `.value`/`.operator`/`.column_id` to the leaf.
_LOCATION_SUBKEYS = (".value", ".operator", ".column_id", ".join", ".filters")


def oqo_location_addresses(oqo, resolver=None) -> dict:
    """Map each OQO filter *location string* (the validator's `location`, e.g.
    `filter_rows[0].filters[1]`) to the decimal address of the node it names —
    for #474 diagnostics (`errors[].path`).

    The validator walks the distributed OQO; addressing lives on the merged OQL
    tree. They are bridged by object identity: `_merge_same_field_items` reuses the
    original leaf objects, so the same leaf the validator flagged is the one
    `build_tree` placed in the tree. Filters only — non-filter locations
    (sort/group_by/sample/page/…) are out of scope (spec §7) and absent here."""
    origins = {}
    stamp_addresses(build_tree(oqo, resolver, origins=origins))
    out = {}

    def visit(node, loc):
        n = origins.get(id(node))
        if n is not None and "addr" in n:
            out[loc] = list(n["addr"])
        if isinstance(node, BranchFilter):
            for j, c in enumerate(node.filters):
                visit(c, f"{loc}.filters[{j}]")

    for i, row in enumerate(oqo.filter_rows or []):
        visit(row, f"filter_rows[{i}]")
    return out


def address_for_location(loc_map: dict, location):
    """Resolve a validator `location` to a decimal address (a list of ints) via the
    `oqo_location_addresses` map, or None. Strips one trailing sub-attribute
    (`.value`/`.operator`/…) so an error on a leaf's value still points at the leaf."""
    if not location:
        return None
    node_loc = location
    for sk in _LOCATION_SUBKEYS:
        if node_loc.endswith(sk):
            node_loc = node_loc[: -len(sk)]
            break
    return loc_map.get(node_loc) or loc_map.get(location)
