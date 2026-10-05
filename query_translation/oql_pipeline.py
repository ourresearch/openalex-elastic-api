"""Canonical text for the pipeline language (oxjob #1530; spec #1512 SYNTAX.md).

    get works where institution is (I63966007); then group those works by author
    where count of those works > (10); then group those works again by year;
    then calculate count, mean FWCI

`render_pipeline(oqo)` renders ANY OQO in this style. Until the launch flips the
default (Jason's call, 2026-10-03: every query switches at launch, old forms are
accepted forever), `oql_lang.render` uses it only for OQOs that the classic form
can't say (`OQO.uses_pipeline`). Beyond the steps, the style differs from classic
in two places, both from the 2026-10-03 decisions:

* filter negation goes on the verb: `type is not (review)`, `institution is not
  (I1 or I2)`, `topic is not in (col_x)` (classic: `type is (not review)`);
* a search is one portable string with capital operators:
  `title-abstract has ((asthma OR wheeze) NOT (pediatric OR child))`.

The tree is the classic `OQLRenderTree` (Invariant A: stringify(tree) == text):
the head reads `get works`, and each step is a `StepDirective` joined by `; then `.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from query_translation import oql_lang as L
from query_translation.oqo import (
    OQO, BranchFilter, GroupBy, LeafFilter, Measure, MeasureFilter)
from query_translation.oql_render_tree import (
    ClauseMeta, ClauseNode, EntityHead, GroupMeta, GroupNode, OQLRenderTree,
    Segment, _stringify_expr)


@dataclass
class StepMeta:
    """What a step does, for consumers of the tree (the website)."""
    step: str                      # "split" | "calculate" | "sample"
    index: Optional[int] = None    # split index (0 = outermost)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {"step": self.step}
        if self.index is not None:
            d["index"] = self.index
        d.update(self.data)
        return d


@dataclass
class StepDirective:
    """One pipeline step after the start: `group those works by year`. `joiner`
    sets it off from what precedes it (`; then `)."""
    prefix: str
    segments: List[Segment]
    meta: StepMeta
    joiner: str = "; then "

    @property
    def type(self) -> str:
        return "step"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "step", "prefix": self.prefix, "joiner": self.joiner,
                "segments": [s.to_dict() for s in self.segments],
                "meta": self.meta.to_dict()}


_MEASURE_SURFACE = {"mean": "mean", "median": "median", "sum": "sum",
                    "min": "min", "max": "max", "percent": "percent"}

# The last step's verb (oxjob #1555, Jason 2026-10-05: "summarize" reads better than
# "calculate"; "using" over "with", which `with seed` already uses). The parser also
# takes `calculate`, `summarize with` and `summarize by`.
SUMMARIZE = "summarize using "


def transitions(n: int) -> List[str]:
    """The word that opens each of n steps after the start (oxjob #1555, Jason
    2026-10-05): one step `then`; two `then`, `finally`; three or more `first`,
    `then` ..., `finally`. Input takes any of them anywhere (they're sugar)."""
    if n <= 0:
        return []
    if n == 1:
        return ["then"]
    if n == 2:
        return ["then", "finally"]
    return ["first"] + ["then"] * (n - 2) + ["finally"]


def _text(s: str) -> Segment:
    return L._seg("text", s)


def _segs_text(segs: List[Segment]) -> str:
    return "".join(s.text for s in segs)


# ---------------------------------------------------------------------------
# Clauses in the pipeline style
# ---------------------------------------------------------------------------
def _search_vtree_text(vt: dict) -> str:
    """A search value tree as a portable string: capital AND / OR, and the
    negated members of an AND written as a trailing `NOT (...)` (`(a OR b) NOT
    (c OR d)`, De Morgan of the canonical NNF `... and not c and not d`)."""
    if vt["node"] == "vleaf":
        text = vt["display"]
        return f"NOT {text}" if vt["negated"] else text

    def child(c):
        t = _search_vtree_text(c)
        return f"({t})" if c["node"] == "vgroup" else t

    kids = vt["children"]
    if vt["join"] == "and":
        pos = [c for c in kids if not (c["node"] == "vleaf" and c["negated"])]
        neg = [c for c in kids if c["node"] == "vleaf" and c["negated"]]
        if pos and neg:
            left = " AND ".join(child(c) for c in pos)
            negs = [dict(c, negated=False) for c in neg]
            right = (negs[0]["display"] if len(negs) == 1
                     else "(" + " OR ".join(c["display"] for c in negs) + ")")
            return f"{left} NOT {right}"
        return " AND ".join(child(c) for c in kids)
    return " OR ".join(child(c) for c in kids)


def _pipeline_clause(cn: ClauseNode) -> ClauseNode:
    """Rewrite one classic clause into the pipeline style (in place of its
    segments; the structural `vtree` is dropped so the formatter keeps it whole)."""
    meta = cn.meta
    segs = cn.segments
    col = next((s for s in segs if s.kind == "column"), None)
    if col is None:
        return cn
    leaf = meta.oqo_ref if isinstance(meta.oqo_ref, LeafFilter) else None
    vt = meta.vtree
    if leaf is not None and leaf.column_id.endswith(".search.semantic"):
        return cn   # `is similar to ("...")` is the same in both styles
    if cn.clause_kind == "text" and meta.operator in ("has",):
        # a search: one portable string inside `has (...)`
        if vt is not None:
            inner = _search_vtree_text(vt)
        elif leaf is not None:
            term = L._render_term(leaf.value, leaf.column_id)
            inner = f"NOT {term}" if leaf.is_negated else term
        else:
            return cn
        new = [col, L._seg("operator", " has "), _text("("),
               L._seg("value", inner, value=meta.value), _text(")")]
        return ClauseNode(segments=new, clause_kind=cn.clause_kind,
                          meta=_meta_without_vtree(meta))
    if meta.operator == "in collection" and leaf is not None:
        val = L._render_value(L._BY_COLUMN.get(leaf.column_id), leaf.value)
        verb = " is not in " if leaf.is_negated else " is in "
        rel = L._RELATION_SET_RENDER.get(leaf.column_id)
        if rel is not None:
            # a collection of works on a relation (oxjob #1535): `it cites works in (col_x)`
            subj, verb = rel[1] if leaf.is_negated else rel[0]
            col = L._seg("column", subj, column_id=leaf.column_id)
        new = [col, L._seg("operator", verb), _text("("),
               L._seg("value", val, value=leaf.value), _text(")")]
        return ClauseNode(segments=new, clause_kind=cn.clause_kind,
                          meta=_meta_without_vtree(meta))
    if meta.operator != "is" or cn.clause_kind == "boolean":
        return cn
    # `x is (not a)` / `x is (not a and not b)` -> `x is not (a)` / `is not (a or b)`
    open_i = next((i for i, s in enumerate(segs) if s.kind == "text" and s.text == "("),
                  None)
    if open_i is None or segs[open_i - 1].kind != "operator":
        return cn
    op_seg = segs[open_i - 1]
    if vt is not None:
        kids = vt["children"] if vt["node"] == "vgroup" else [vt]
        if not (vt["node"] == "vgroup" and vt["join"] == "and"
                and all(c["node"] == "vleaf" and c["negated"] for c in kids)):
            return cn
        values: List[Segment] = []
        for i, c in enumerate(kids):
            if i:
                values.append(_text(" or "))
            values.extend(c["_segs"])
    else:
        neg_i = next((i for i, s in enumerate(segs) if s.kind == "negation"), None)
        if neg_i is None:
            return cn
        values = segs[neg_i + 1:-1]
    verb = op_seg.text.replace(" is ", " is not ") if " is " in op_seg.text else None
    if verb is None:
        return cn   # row-subject verbs keep the value-level `not` until Rung 2
    new = segs[:open_i - 1] + [L._seg("operator", verb), _text("(")] + values + [_text(")")]
    return ClauseNode(segments=new, clause_kind=cn.clause_kind,
                      meta=_meta_without_vtree(meta))


def _meta_without_vtree(meta: ClauseMeta) -> ClauseMeta:
    from dataclasses import replace
    return replace(meta, vtree=None)


def _pipeline_expr(node):
    if isinstance(node, ClauseNode):
        return _pipeline_clause(node)
    if isinstance(node, GroupNode):
        node.children = [_pipeline_expr(c) for c in node.children]
    return node


def where_node(filters: List, resolver=None, top: bool = True):
    """The pipeline-style ExprNode for an implicit-AND list of filters (or one)."""
    rows = L._merge_same_field_items(list(filters), "and")
    if len(rows) == 1:
        return _pipeline_expr(L._filter_node(rows[0], top=top, resolver=resolver))
    children = [_pipeline_expr(L._filter_node(f, top=False, resolver=resolver))
                for f in rows]
    if top:
        return GroupNode(join="and", children=children, prefix="", suffix="",
                         joiner=" and ", meta=GroupMeta(implicit=True))
    return GroupNode(join="and", children=children, prefix="(", suffix=")",
                     joiner=" and ", meta=GroupMeta(implicit=False))


def _expr_text(filters, resolver=None, top=True) -> str:
    if isinstance(filters, (LeafFilter, BranchFilter)):
        filters = (L._flatten_and(filters)
                   if isinstance(filters, BranchFilter) and filters.join == "and"
                   and not filters.is_negated else [filters])
    return _stringify_expr(where_node(filters, resolver, top=top))


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def measure_text(m: Measure, noun: str) -> str:
    """`count`, `mean FWCI`, `percent open access`, `percent of those works`."""
    if m.measure == "count":
        return "count"
    if m.measure == "percent_of_those":
        return f"percent of those {noun}"
    if m.measure == "value":          # a group's own field, e.g. an author's h-index
        return L._oql_field(m.column_id)[0]
    return f"{_MEASURE_SURFACE[m.measure]} {L._oql_field(m.column_id)[0]}"


def _number(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _group_where_text(node, ctx: dict, resolver=None, top=True) -> str:
    """A group filter: measures on the groups' works, and the group's own fields."""
    noun = ctx["noun"]
    if isinstance(node, MeasureFilter):
        what = "count" if node.measure == "count" else measure_text(
            Measure(node.measure, node.column_id), noun)
        op = "is not" if node.is_negated and node.operator == "is" else node.operator
        return f"{what} of those {noun} {op} ({_number(node.value)})"
    if isinstance(node, BranchFilter):
        # A same-subject set clause (`co-author is not (A or B)`, `that author is
        # (A1 or A2)`) renders whole; otherwise join the parts.
        own = _set_clause_text(node, ctx, resolver)
        if own is not None:
            return own
        # merge same-subject set leaves back into one clause: in an AND the NNF
        # of `co-author is not (A1 or A2)`, in an OR `that author is (A1 or A2)`
        kids, merged = [], {}
        for c in node.filters:
            if (isinstance(c, LeafFilter) and c.column_id in ("co_author", "collaborator",
                                                              "ids.openalex")
                    and c.is_negated == (node.join == "and")):
                if c.column_id in merged:
                    merged[c.column_id].filters.append(c)
                    continue
                merged[c.column_id] = BranchFilter(node.join, [c])
                kids.append(merged[c.column_id])
            else:
                kids.append(c)
        kids = [k.filters[0] if isinstance(k, BranchFilter) and k in merged.values()
                and len(k.filters) == 1 else k for k in kids]
        parts = [_group_where_text(c, ctx, resolver, top=False) for c in kids]
        inner = f" {node.join} ".join(parts)
        if node.is_negated:
            return f"not ({inner})"
        return inner if top else f"({inner})"
    own = _set_clause_text(node, ctx, resolver)
    if own is not None:
        return own
    # an ordinary clause on the group entity's own fields
    tok = L._RENDER_ENTITY.set(ctx["group_entity"])
    try:
        return _stringify_expr(where_node([node], resolver, top=top))
    finally:
        L._RENDER_ENTITY.reset(tok)


_SET_SUBJECTS = {"co_author": "co-author", "collaborator": "collaborator"}


def _set_clause_text(node, ctx, resolver=None) -> Optional[str]:
    """`that author is not in (col_x)`, `that author is (A1 or A2)`, `co-author is
    not (A1)`: the group's own id or a co-authorship relation. None otherwise."""
    leaves = [node] if isinstance(node, LeafFilter) else (
        node.filters if isinstance(node, BranchFilter) else [])
    if not leaves or not all(isinstance(x, LeafFilter) for x in leaves):
        return None
    cols = {x.column_id for x in leaves}
    if len(cols) != 1:
        return None
    col = cols.pop()
    if col == "collection" and isinstance(node, LeafFilter):
        subject = f"that {ctx['singular']}"
        verb = "is not in" if node.is_negated else "is in"
        return f"{subject} {verb} ({node.value})"
    if col == "ids.openalex" and ctx.get("singular"):
        subject = f"that {ctx['singular']}"
    elif col in _SET_SUBJECTS:
        subject = _SET_SUBJECTS[col]
    else:
        return None
    negs = {x.is_negated for x in leaves}
    if len(negs) != 1:
        return None
    negated = negs.pop()
    if isinstance(node, BranchFilter):
        # positive OR (`is (A or B)`) or the NNF of `is not (A or B)` (AND of nots)
        if node.join != ("and" if negated else "or"):
            return None
    vals = " or ".join(str(x.value) for x in leaves)
    return f"{subject} {'is not' if negated else 'is'} ({vals})"


def _split_segments(g: GroupBy, noun: str, again: bool, resolver=None) -> Tuple[str, List[Segment]]:
    lead = f"group those {noun}{' again' if again else ''} "
    if g.conditions is not None:
        items = ", ".join(f"({_expr_text(c, resolver)})" for c in g.conditions)
        return lead + "into ", [_text(f"({items})")]
    name = L._oql_field(g.column_id)[0] if g.column_id else ""
    col = L._seg("column", name, column_id=g.column_id)
    if g.bins is not None:
        if "at" in g.bins:
            tail = "bins at (" + ", ".join(_number(e) for e in g.bins["at"]) + ")"
        else:
            tail = f"bins of ({_number(g.bins['of'])})"
        return lead + "into ", [col, _text(f" {tail}")]
    if g.values is not None:
        if g.column_id.endswith(".search"):
            items = ", ".join(f"({_search_item_text(v)})" for v in g.values)
            return lead + "by ", [col, _text(f" search in ({items})")]
        vals = []
        for i, v in enumerate(g.values):
            if i:
                vals.append(_text(", "))
            vsegs, _ent = L._value_segments(L._BY_COLUMN.get(g.column_id), v,
                                            g.column_id, resolver)
            vals.extend(vsegs)
        return lead + "by ", [col, _text(" in (")] + vals + [_text(")")]
    return lead + "by ", [col]


def _search_item_text(tree) -> str:
    """One listed search as its portable string (no outer parentheses)."""
    node = L._filter_node(tree, top=True)
    node = _pipeline_expr(node)
    text = _stringify_expr(node)
    # `<field> has (<string>)` -> `<string>`
    i = text.find(" has (")
    if i >= 0 and text.endswith(")"):
        return text[i + len(" has ("):-1]
    return text


def build_pipeline_tree(oqo: OQO, resolver=None) -> OQLRenderTree:
    tok = L._RENDER_ENTITY.set(oqo.get_rows)
    try:
        return _build(oqo, resolver)
    finally:
        L._RENDER_ENTITY.reset(tok)


def _start_ids(f) -> Optional[List]:
    """The ids of a `get each <noun> in (...)` start: an `ids.openalex` leaf or OR
    of leaves, or a collection; None for anything else."""
    leaves = [f] if isinstance(f, LeafFilter) else (
        f.filters if isinstance(f, BranchFilter) and f.join == "or" and not f.is_negated
        else [])
    if not leaves or not all(isinstance(x, LeafFilter) and x.column_id == "ids.openalex"
                             and not x.is_negated and x.operator == "is"
                             and not isinstance(x.value, OQO) for x in leaves):
        if isinstance(f, LeafFilter) and f.operator == "in collection" and not f.is_negated:
            return [f.value]
        return None
    return [x.value for x in leaves]


def _expr_text_in(entity: str, tree, resolver=None) -> str:
    """A filter tree's text in another entity's namespace (a walk's `where`)."""
    tok = L._RENDER_ENTITY.set(entity)
    try:
        return _expr_text(tree, resolver)
    finally:
        L._RENDER_ENTITY.reset(tok)


def _walk_steps(oqo: OQO, resolver=None) -> Tuple[List[StepDirective], str]:
    """The walk steps (oxjob #1535) and the plural noun of what the query holds after
    them: `get each author of those works where h-index > (20)`, `get all that
    author's works`."""
    from query_translation.walks import entity_for_link, plural, possessive, singular
    cur, each = oqo.get_rows, bool(oqo.each)
    steps: List[StepDirective] = []
    for i, w in enumerate(oqo.walks):
        here = L._plural_noun(cur)
        if w.to is None:
            ent = entity_for_link(w.column_id) or "works"
            text = (f"get each {singular(ent)} of those {here}" if w.each
                    else f"get {plural(ent)} of those {here}")
            if w.where is not None:
                text += " where " + _expr_text_in(ent, w.where, resolver)
            cur, each = ent, w.each
        else:
            text = f"get all {possessive(cur, each)} works"
            if w.where is not None:
                text += " where " + _expr_text_in(w.to, w.where, resolver)
            cur = w.to
        steps.append(StepDirective(prefix="", segments=[_text(text)],
                                   meta=StepMeta("walk", index=i, data=w.to_dict())))
    return steps, L._plural_noun(cur)


def _build(oqo: OQO, resolver=None) -> OQLRenderTree:
    from query_translation.walks import singular
    entity = oqo.get_rows
    noun = L._plural_noun(entity)
    head_text = f"get {entity.lower()}"
    filters = list(oqo.filter_rows)
    if oqo.each:
        # `get each institution in (I1, I2)` (oxjob #1535)
        head_text = f"get each {singular(entity)}"
        ids = _start_ids(filters[0]) if filters else None
        if ids is not None:
            head_text += " in (" + ", ".join(str(v) for v in ids) + ")"
            filters = filters[1:]
    head = EntityHead(id=entity, text=head_text)
    corpus_phrase = ""
    if getattr(oqo, "corpus", "core") and oqo.corpus != "core":
        corpus_phrase = f" ({L.CORPUS_CANONICAL_PHRASE.get(oqo.corpus, oqo.corpus)})"
    where_keyword, where = "", None
    if filters:
        where_keyword = " where "
        where = where_node(filters, resolver, top=True)

    steps: List[StepDirective] = []
    if oqo.sample:
        segs = [L._seg("value", f"({oqo.sample})", value=oqo.sample),
                _text(f" of those {noun}")]
        if oqo.seed is not None:
            segs.append(_text(f" with seed ({oqo.seed})"))
        steps.append(StepDirective(prefix="sample ", segments=segs,
                                   meta=StepMeta("sample", data={"n": oqo.sample})))
    tok = None
    if oqo.walks:
        from query_translation.oqo import result_entity
        walk_steps, noun = _walk_steps(oqo, resolver)
        steps.extend(walk_steps)
        entity = result_entity(oqo)
        # splits and calculations name the fields of what the walks reached
        tok = L._RENDER_ENTITY.set(entity)
    try:
        _later_steps(oqo, steps, entity, noun, resolver)
    finally:
        if tok is not None:
            L._RENDER_ENTITY.reset(tok)
    for d, word in zip(steps, transitions(len(steps))):
        d.joiner = f"; {word}, "
    return OQLRenderTree(version="1.0", entity=head, where_keyword=where_keyword,
                         where=where, directives=steps, corpus_phrase=corpus_phrase)


def _later_steps(oqo: OQO, steps: List[StepDirective], entity: str, noun: str,
                 resolver=None):
    """The splits and the calculation."""
    for i, g in enumerate(oqo.group_by):
        prefix, segs = _split_segments(g, noun, again=i > 0, resolver=resolver)
        if g.where is not None:
            from query_translation.oql_lang import _group_entity, _singular_noun
            ge = _group_entity(g, entity)
            ctx = {"noun": noun, "group_entity": ge,
                   "singular": _singular_noun(ge) if ge else None}
            segs = segs + [_text(" where " + _group_where_text(g.where, ctx, resolver))]
        steps.append(StepDirective(prefix=prefix, segments=segs,
                                   meta=StepMeta("split", index=i, data=g.to_dict())))
    if oqo.calculate:
        text = ", ".join(measure_text(m, noun) for m in oqo.calculate)
        steps.append(StepDirective(
            prefix=SUMMARIZE, segments=[_text(text)],
            meta=StepMeta("calculate", data={
                "measures": [dict(m.to_dict(), key=m.key) for m in oqo.calculate]})))


def stringify_pipeline(tree: OQLRenderTree) -> str:
    parts = [tree.entity.text, tree.corpus_phrase, tree.where_keyword]
    if tree.where is not None:
        parts.append(_stringify_expr(tree.where))
    for d in tree.directives:
        parts.append(d.joiner + d.prefix + _segs_text(d.segments))
    return "".join(parts)


def format_pipeline(tree: OQLRenderTree, width: int = None) -> str:
    """One line when it fits; else the start and each step on their own line,
    each line but the last ending in `;` (whitespace-blind parser: same OQO)."""
    width = width or L.FORMAT_WIDTH
    flat = stringify_pipeline(tree)
    if len(flat) <= width:
        return flat
    head = f"{tree.entity.text}{tree.corpus_phrase}{tree.where_keyword}"
    if tree.where is not None:
        head += L._fmt_expr(tree.where, L._INDENT, len(head), width)
    lines = [head]
    for d in tree.directives:
        lines[-1] += ";"
        lines.extend(_wrap_step(f"{d.joiner[2:]}{d.prefix}{_segs_text(d.segments)}",
                                width))
    return "\n".join(lines)


def _wrap_step(line: str, width: int) -> List[str]:
    """A step over the width: its group filter on the next lines, one condition
    per line (`  where ...` / `  and ...`), split only at top-level connectives."""
    if len(line) <= width:
        return [line]
    i = line.find(" where ")
    if i < 0:
        return [line]
    head, rest = line[:i], line[i + len(" where "):]
    parts, conns = [], []
    depth, quoted, start, j = 0, False, 0, 0
    while j < len(rest):
        c = rest[j]
        if c == '"':
            quoted = not quoted
        elif not quoted and c == "(":
            depth += 1
        elif not quoted and c == ")":
            depth -= 1
        elif not quoted and depth == 0:
            for conn in (" and ", " or "):
                if rest.startswith(conn, j):
                    parts.append(rest[start:j])
                    conns.append(conn.strip())
                    j += len(conn)
                    start = j
                    break
            else:
                j += 1
                continue
            continue
        j += 1
    parts.append(rest[start:])
    out = [head, f"  where {parts[0]}"]
    out.extend(f"  {conn} {p}" for conn, p in zip(conns, parts[1:]))
    return out


def render_pipeline_tree(oqo: OQO, resolver=None):
    tree = build_pipeline_tree(oqo, resolver)
    return format_pipeline(tree), tree


def render_pipeline(oqo: OQO, resolver=None) -> str:
    return render_pipeline_tree(oqo, resolver)[0]


def render_pipeline_line(oqo: OQO, resolver=None) -> str:
    """The canonical text on one line (a query inside another's parentheses)."""
    return stringify_pipeline(build_pipeline_tree(oqo, resolver))
