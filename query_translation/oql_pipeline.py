"""Canonical text for the pipeline language (oxjob #1530; spec #1512 SYNTAX.md).

    get works where institution is (I63966007); then group those works by author
    where count of those works > (10); then group those works again by year;
    then, summarize using count, mean FWCI

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

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from query_translation import oql_lang as L
from query_translation.oqo import (
    OQO, AffiliationFilter, BranchFilter, GroupBy, LeafFilter, Measure, MeasureFilter)
from query_translation.oql_render_tree import (
    ClauseMeta, ClauseNode, EntityHead, GroupMeta, GroupNode, OQLRenderTree,
    Segment, _stringify_expr)


@dataclass
class StepMeta:
    """What a step does, for consumers of the tree (the website)."""
    step: str                      # "split" | "compare" | "calculate" | "sample" | ...
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
# takes `summarize with`, `summarize by` and a bare `summarize`; `calculate` is gone
# (Jason 2026-10-08: it fails like any other word that doesn't start a step).
SUMMARIZE = "summarize using "


def english_list(items: List[str]) -> str:
    """`a`, `a and b`, `a, b, and c` (the Oxford comma; Jason 2026-10-05)."""
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def transitions(n: int) -> List[str]:
    """The word that opens each of n steps after the start (oxjob #1555, Jason
    2026-10-08): `then` for each step, `finally` for the last of two or more. No
    `first`: the `get` step is the first. Input takes `first`, `next`, `lastly`
    anywhere too (they're sugar)."""
    if n <= 0:
        return []
    if n == 1:
        return ["then"]
    return ["then"] * (n - 1) + ["finally"]


def _text(s: str) -> Segment:
    return L._seg("text", s)


def _segs_text(segs: List[Segment]) -> str:
    return "".join(s.text for s in segs)


# ---------------------------------------------------------------------------
# Clauses in the pipeline style
# ---------------------------------------------------------------------------
_WITHIN = re.compile(r"^within (\d+) \((.*)\)$")


def proximity_words(text: str, alone: bool = True) -> str:
    """`within 3 (smart, phone)` -> `smart and phone within 3 words of each other`
    (Jason 2026-10-09: "Englishify that"); in parentheses unless it is the whole search."""
    m = _WITHIN.match(text or "")
    if m is None:
        return text
    items = re.findall(r'"[^"]*"|[^,\s][^,]*', m.group(2))
    words = english_list([x.strip() for x in items])
    out = f"{words} within {m.group(1)} words of each other"
    return out if alone else f"({out})"


def _search_vtree_text(vt: dict) -> str:
    """A search value tree as a portable string: capital AND / OR, and the
    negated members of an AND written as a trailing `NOT (...)` (`(a OR b) NOT
    (c OR d)`, De Morgan of the canonical NNF `... and not c and not d`)."""
    if vt["node"] == "vleaf":
        text = proximity_words(vt["display"], alone=False)
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
            right = (proximity_words(negs[0]["display"], alone=False) if len(negs) == 1
                     else "(" + " OR ".join(proximity_words(c["display"], alone=False)
                                            for c in negs) + ")")
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
            if (term == f'"{leaf.value}"' and not leaf.column_id.endswith(".exact")
                    and str(leaf.value).lower() in _BARE_RESERVED_SEARCH):
                # a one-word stemmed search for a reserved word reads bare inside
                # the parentheses; quoted it would come back an EXACT search (#1555)
                term = str(leaf.value)
            inner = (f"NOT {proximity_words(term, alone=False)}" if leaf.is_negated
                     else proximity_words(term))
        else:
            return cn
        new = [col, L._seg("operator", " has "), _text("("),
               L._seg("value", inner, value=meta.value), _text(")")]
        return ClauseNode(segments=new, clause_kind=cn.clause_kind,
                          meta=_meta_without_vtree(meta))
    if meta.operator == "in collection" and leaf is not None:
        val = L._render_value(L._BY_COLUMN.get(leaf.column_id), leaf.value)
        verb = " is not in the set " if leaf.is_negated else " is in the set "
        rel = L._RELATION_SET_RENDER.get(leaf.column_id)
        if rel is not None:
            # a collection of works on a relation (oxjob #1535): `it cites works in (col_x)`
            subj, verb = rel[1] if leaf.is_negated else rel[0]
            col = L._seg("column", subj, column_id=leaf.column_id)
        # a saved collection reads `in the collection` (Jason 2026-10-08: the
        # signpost says whether it's a collection or a set defined by a query)
        verb = verb.replace("in the set", "in the collection")
        new = [col, L._seg("operator", verb),
               L._seg("value", val, value=leaf.value, column_id=leaf.column_id)]
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


# Reserved words that a one-word search reads back as a stemmed search when bare
# inside `has (...)` (probed 2026-10-06). `not` and `within` can't stand alone there;
# a stemmed search for them stays quoted (exact), which nobody needs.
_BARE_RESERVED_SEARCH = {"group", "sample", "stemmed", "and", "or", "&"}


def _link_name(name: str) -> str:
    """A display name as a link's text: one line, square brackets as parentheses
    (the parser never reads it, so tidying it changes nothing)."""
    return " ".join(name.split()).replace("[", "(").replace("]", ")")


def _entity_type(column_id: Optional[str]) -> Optional[str]:
    if not column_id or column_id in L._SELF_ID_COLUMNS:
        return None
    fld = L._BY_COLUMN.get(column_id)
    if fld is not None and fld.kind in ("search", "collection", "num", "date", "bool"):
        return None
    return L.entity_type_for_column(column_id)


def _name_column(ns: str) -> Optional[str]:
    """A column whose values are `ns` IDs, to ask the (value, column) resolver."""
    from query_translation.walks import WALK_LINKS
    return {"works": "cited_by", "collections": "collection"}.get(ns) or WALK_LINKS.get(ns)


def link_text(value, ns: str, resolver=None, in_list: bool = False, name=None) -> str:
    """One entity value as a Markdown link (oxjob #1555): `[name](ID)`, the name from
    `name`, the resolver, or the closed vocabulary's table; with none, `(ID)` (a bare
    ID inside a list's own parentheses). Collections (`col_x`) name themselves the
    same way, through the resolver."""
    from query_translation.oql_renderer import _builtin_name
    text = str(value)
    if name is None and resolver is not None and _name_column(ns):
        try:
            name = resolver(value, _name_column(ns)) or None
        except Exception:  # noqa: BLE001 (a name is decoration; never fail on it)
            name = None
    if name is None and isinstance(value, str) and not value.startswith("col_"):
        name = _builtin_name(ns, value)
    if name:
        return f"[{_link_name(name)}]({text})"
    return text if in_list else f"({text})"


def _links(segs: List[Segment], in_list: bool, resolver=None) -> List[Segment]:
    """Every entity value as a Markdown link (oxjob #1555, Jason 2026-10-08):
    `[Massachusetts Institute of Technology](I63966007)`, `[Kenya](KE)`,
    `[article](article)`. The name comes from the resolver, else the closed
    vocabulary's table; with none, the link is just `(I63966007)` (a bare ID inside
    a list's own parentheses)."""
    from query_translation.oql_renderer import _builtin_name
    segs = list(segs)
    out: List[Segment] = []
    i = 0
    while i < len(segs):
        s = segs[i]
        col = s.meta.column_id if s.kind == "value" and s.meta else None
        if col is not None and isinstance(s.meta.value, str) \
                and s.meta.value.startswith("col_"):
            # a collection: `[Climate topics](col_abc123)` (oxjob #1555)
            out.append(Segment(kind="value", meta=s.meta, text=link_text(
                s.meta.value, "collections", resolver, in_list)))
            i += 1
            continue
        ns = _entity_type(col)
        if ns is None:
            out.append(s)
            i += 1
            continue
        nxt = segs[i + 2] if i + 2 < len(segs) else None
        name = None
        if (nxt is not None and nxt.kind == "id" and segs[i + 1].kind == "text"
                and segs[i + 1].text == " "):
            if nxt.text != L._NO_ENTITY_ANNOTATION and nxt.meta is not None:
                name = nxt.meta.full_name or nxt.meta.entity_display_name
            i += 3
        else:
            i += 1
        if name is None and isinstance(s.meta.value, str):
            name = _builtin_name(ns, s.meta.value)
        if name:
            text = f"[{_link_name(name)}]({s.text})"
        else:
            text = s.text if in_list else f"({s.text})"
        out.append(Segment(kind="value", text=text, meta=s.meta))
    return out


def _bare_values(cn: ClauseNode, resolver=None) -> ClauseNode:
    """Today's value forms (oxjob #1555): entity values as Markdown links (Jason
    2026-10-08), and a single value without its parentheses (2026-10-06): `year >=
    2020`, `type is not [review](review)`, `institution is [Massachusetts Institute
    of Technology](I63966007)`. Lists of two or more keep one pair; searches, sets
    (`in (...)`) and row-subject relations (`it cites (...)`) keep theirs."""
    n_values = sum(1 for x in cn.segments if x.kind == "value")
    col0 = next((x for x in cn.segments if x.kind == "column"), None)
    # a relation keeps its own parentheses (`it cites (W1)`), so a nameless link
    # inside them is the bare id, not `((W1))`
    relation = (col0 is not None and col0.text.startswith("it")
                and (cn.meta.operator or "") != "in collection")
    out = _links(cn.segments, in_list=n_values > 1 or relation, resolver=resolver)
    meta = cn.meta
    if len(out) != len(cn.segments) or any(x is not y for x, y in zip(out, cn.segments)):
        # the multi-line formatter lays value lists out from the vtree's own
        # segments: keep a rewritten clause whole instead
        meta = _meta_without_vtree(meta)
    col = next((x for x in out if x.kind == "column"), None)
    op_i = next((k for k, x in enumerate(out) if x.kind == "operator"), None)
    keeps = (cn.clause_kind == "text" or col is None or col.text.startswith("it")
             or (cn.meta.operator or "") in ("in collection", "in", "has")
             or op_i is None or op_i + 1 >= len(out))
    if not keeps and out[op_i + 1].kind == "text" and out[op_i + 1].text == "(" \
            and out[-1].kind == "text" and out[-1].text == ")":
        inner = out[op_i + 2:-1]
        single = (sum(1 for x in inner if x.kind == "value") == 1
                  and not any(x.kind in ("negation",) or (x.kind == "text" and x.text.strip())
                              for x in inner))
        if single:
            out = out[:op_i + 1] + inner
    return ClauseNode(segments=out, clause_kind=cn.clause_kind, meta=meta)


def _meta_without_vtree(meta: ClauseMeta) -> ClauseMeta:
    return replace(meta, vtree=None)


def _flag_sentence(cn: ClauseNode) -> Optional[ClauseNode]:
    """A yes/no flag as its sentence (Jason 2026-10-08): `it's not retracted`, `it has
    a DOI`; flags with no sentence keep `<flag> is true|false`."""
    from query_translation.oql_bool_phrases import BOOL_PHRASES
    meta = cn.meta
    if cn.clause_kind != "boolean" or meta is None or not isinstance(meta.value, bool) \
            or (meta.operator or "is") != "is":
        return None
    pair = BOOL_PHRASES.get(meta.column_id)
    if pair is None:
        return None
    return ClauseNode(segments=[L._seg("column", pair[0] if meta.value else pair[1],
                                       column_id=meta.column_id)],
                      clause_kind=cn.clause_kind, meta=_meta_without_vtree(meta))


# Years and dates in words (Jason 2026-10-09: "published since 2020", then dates the
# same way and "added since" for the created date; reading test in oxjob #1555 EXPLORE.md
# "Words for symbols"). `after` is written for years only: for a date it's ambiguous
# (does it include the day?), so a strict date bound keeps its symbol and the parser
# refuses `after <date>`.
COMPARISON_WORDS = {">=": "since", ">": "after", "<=": "through", "<": "before"}
# low bound column -> (high bound column, low op, high op): pairs that read `<verb> from A
# through B` (a date's inclusive bounds are their own columns, leaves with `is`)
_RANGE_PAIRS = {"publication_year": ("publication_year", ">=", "<="),
                "from_publication_date": ("to_publication_date", "is", "is"),
                "from_created_date": ("to_created_date", "is", "is")}


def _phrase_entry(column: str) -> Optional[Tuple[str, str]]:
    """(verb, "year"|"date") for a column said in words (`published`, `added`), from the
    parser's PHRASE_VERBS and the field registry (a date bound's axis word), else None."""
    fld = L._BY_COLUMN.get(column)
    return L.PHRASE_OF_WORD.get(fld.date_axis or fld.oql) if fld is not None else None


def _phrase_value_ok(kind: str, text: str) -> bool:
    return L.value_kind(text.strip()) == kind


def _phrase(verb: str, column: str, word: str) -> List:
    return [L._seg("column", verb, column_id=column), L._seg("operator", f" {word} ")]


# Every other number reads in words too (Jason 2026-10-09: "always emit words so that
# we're consistent"); the symbols stay accepted input.
NUMBER_WORDS = {op: f"is {w}" for op, w in L.NUMBER_WORDS.items()}   # the parser reads them


def _in_words(cn: ClauseNode) -> Optional[ClauseNode]:
    """A comparison in words: `year >= 2020` -> `published since 2020`, `year is 2023` ->
    `published in 2023`, `date is 2021-06-01` -> `published on 2021-06-01`, `created date
    >= 2025-01-01` -> `added since 2025-01-01`, `h-index > 30` -> `h-index is above 30`.
    A negation keeps its `not` in front (`not published since 2015`)."""
    meta, segs = cn.meta, cn.segments
    if meta is None:
        return None
    neg = list(segs[:1]) if segs and segs[0].kind == "negation" else []
    body = segs[len(neg):]
    if len(body) < 3 or body[1].kind != "operator":
        return None
    vals = list(body[2:])
    if len(vals) == 4 and vals[0].text == "(" and vals[1].kind == "negation" and vals[3].text == ")":
        neg, vals = [vals[1]], [vals[2]]      # `year is not 2020` -> `not published in 2020`
    if len(vals) == 3 and vals[0].text == "(" and vals[2].text == ")":
        vals = [vals[1]]                      # one value, bare
    op, comparison, head = meta.operator, cn.clause_kind == "comparison", None
    entry = _phrase_entry(meta.column_id)
    if entry is not None and all(_phrase_value_ok(entry[1], sg.text)
                                 for sg in vals if sg.kind == "value"):
        verb, kind = entry
        if comparison and op in COMPARISON_WORDS and not (kind == "date" and op == ">"):
            word = COMPARISON_WORDS[op]
        elif (op or "is") == "is" and body[1].text == " is ":
            word = "in" if kind == "year" else "on"
        else:
            word = None
        if word is not None:
            head = _phrase(verb, meta.column_id, word)
    if head is None and comparison and op in NUMBER_WORDS:
        head = [body[0], L._seg("operator", f" {NUMBER_WORDS[op]} ")]
    if head is None:
        return None
    return ClauseNode(segments=neg + head + vals, clause_kind=cn.clause_kind, meta=meta)


def _phrase_ranges(rows: List) -> List:
    """`year >= 2015 and year <= 2024` side by side -> one `published from 2015 through
    2024` clause; dates the same (`date >= ... and date <= ...`), created dates as `added
    from ... through ...`. Both bounds inclusive; a strict bound keeps its own phrase so
    the echo reads back to the same query."""
    def bound(f, column, op):
        return (isinstance(f, LeafFilter) and f.column_id == column and f.operator == op
                and not f.is_negated
                and _phrase_value_ok(_phrase_entry(column)[1], str(f.value)))
    out, i = [], 0
    while i < len(rows):
        a, b = rows[i], rows[i + 1] if i + 1 < len(rows) else None
        col = getattr(a, "column_id", None)
        if col in _RANGE_PAIRS:
            hi_col, lo_op, hi_op = _RANGE_PAIRS[col]
            if bound(a, col, lo_op) and bound(b, hi_col, hi_op) and a.value <= b.value:
                out.append(_range_node(a, b))
                i += 2
                continue
        out.append(a)
        i += 1
    return out


def _range_node(a: LeafFilter, b: LeafFilter) -> ClauseNode:
    verb = _phrase_entry(a.column_id)[0]
    return ClauseNode(
        segments=_phrase(verb, a.column_id, "from") + [
            L._seg("value", str(a.value), value=a.value), L._seg("operator", " through "),
            L._seg("value", str(b.value), value=b.value)],
        clause_kind="comparison",
        meta=ClauseMeta(column_id=a.column_id, operator="range", value=[a.value, b.value],
                        column_display_name=verb))


def _pipeline_expr(node, resolver=None):
    if isinstance(node, ClauseNode):
        return (_flag_sentence(node) or _in_words(node)
                or _bare_values(_pipeline_clause(node), resolver))
    if isinstance(node, GroupNode):
        node.children = [_pipeline_expr(c, resolver) for c in node.children]
    return node


def where_node(filters: List, resolver=None, top: bool = True):
    """The pipeline-style ExprNode for an implicit-AND list of filters (or one)."""
    rows = _phrase_ranges(L._merge_same_field_items(list(filters), "and"))

    def node(f, top_):
        if isinstance(f, ClauseNode):         # a year or date range, already a clause
            return f
        return _pipeline_expr(L._filter_node(f, top=top_, resolver=resolver), resolver)
    if len(rows) == 1:
        return node(rows[0], top)
    children = [node(f, False) for f in rows]
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
        return L.own_field_word(m.column_id) or L._oql_field(m.column_id)[0]
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
        if node.operator in NUMBER_WORDS:     # `count of those works is above 5`
            lead = "not " if node.is_negated else ""
            return f"{lead}{what} of those {noun} {NUMBER_WORDS[node.operator]} {_number(node.value)}"
        op = "is not" if node.is_negated and node.operator == "is" else node.operator
        return f"{what} of those {noun} {op} {_number(node.value)}"
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
        verb = "is not in the collection" if node.is_negated else "is in the collection"
        return f"{subject} {verb} {link_text(node.value, 'collections', resolver)}"
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
    ns = (ctx.get("group_entity") if col == "ids.openalex"
          else L.entity_type_for_column(col)) or "works"
    vals = " or ".join(link_text(x.value, ns, resolver, in_list=len(leaves) > 1)
                       for x in leaves)
    if len(leaves) > 1:
        vals = f"({vals})"
    return f"{subject} {'is not' if negated else 'is'} {vals}"


def _split_segments(g: GroupBy, noun: str, again: bool, resolver=None) -> Tuple[str, List[Segment]]:
    lead = f"group those {noun}{' again' if again else ''} "
    if g.conditions is not None:
        # `into (institution is [KU Leuven](I99464096), country is [Belgium](BE))`
        # (oxjob #1555); each condition's own parentheses stay accepted on input
        items = ", ".join(_expr_text(c, resolver) for c in g.conditions)
        return lead + "into ", [_text(f"({items})")]
    name = L._oql_field(g.column_id)[0] if g.column_id else ""
    col = L._seg("column", name, column_id=g.column_id)
    if g.bins is not None:
        if "at" in g.bins:
            tail = "bins at (" + ", ".join(_number(e) for e in g.bins["at"]) + ")"
        else:
            tail = f"bins of {_number(g.bins['of'])}"
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
            vals.extend(_links(vsegs, in_list=len(g.values) > 1))
        return lead + "by ", [col, _text(" in (")] + vals + [_text(")")]
    return lead + "by ", [col]


# ---------------------------------------------------------------------------
# Comparisons (oxjob #1555, Jason 2026-10-08)
# ---------------------------------------------------------------------------
_LINK_OR_QUOTE = re.compile(r'\[[^\]]*\]\([^)]*\)|"[^"]*"')


def is_compare_split(g: GroupBy) -> bool:
    """A split that lists what it compares: values, searches or conditions."""
    return g.conditions is not None or (g.values is not None and g.bins is None)


def _set_spans(text: str) -> List[Tuple[int, int]]:
    """Where each `in the set (...)` query sits in `text`, parentheses included."""
    spans = []
    for m in re.finditer(r"\bset \(", text):
        depth, j, quoted = 0, m.end() - 1, False
        while j < len(text):
            c = text[j]
            if c == '"':
                quoted = not quoted
            elif not quoted and c == "(":
                depth += 1
            elif not quoted and c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((m.end() - 1, j + 1))
    return spans


def _drop_is(text: str) -> str:
    """`institution is [MIT](I1)` -> `institution [MIT](I1)`: in a comparison `is`
    goes unsaid (`is not` stays). Names, quoted strings and the query inside `in the
    set (...)` (a query of its own, oxjob #1555) are left alone."""
    keep = [(m.start(), m.end()) for m in _LINK_OR_QUOTE.finditer(text)] + _set_spans(text)
    out, last = [], 0
    for a, b in sorted(keep):
        if a < last:
            continue        # inside a set already kept
        out.append(re.sub(r" is (?!not\b)", " ", text[last:a]))
        out.append(text[a:b])
        last = b
    out.append(re.sub(r" is (?!not\b)", " ", text[last:]))
    return "".join(out)


def _compare_item(tree, resolver=None) -> Tuple[Optional[str], str]:
    """One compared condition as (field it can share with its neighbour, rest)."""
    if isinstance(tree, LeafFilter) and isinstance(tree.value, bool) \
            and tree.operator == "is" and not tree.is_negated:
        name = L._oql_field(tree.column_id)[0]
        return None, name if tree.value else f"not {name}"
    text = _expr_text(tree, resolver)
    if isinstance(tree, LeafFilter) and tree.operator == "is" and not tree.is_negated:
        name = L._oql_field(tree.column_id)[0]
        if text.startswith(name + " is "):
            return name, text[len(name) + 4:]
    text = _drop_is(text)
    if isinstance(tree, BranchFilter):
        leaves = tree.filters
        if all(isinstance(x, LeafFilter) for x in leaves) \
                and len({x.column_id for x in leaves}) == 1:
            name = L._oql_field(leaves[0].column_id)[0]
            if text.startswith(name + " (") and text.endswith(")"):
                # `country ([China](CN) and [US](US))` -> `(country [China](CN) and ...)`
                return None, f"({name} {text[len(name) + 2:-1]})"
        if " and " not in text and " or " not in text:
            return None, text                 # one phrase: `published from 2010 through 2014`
        return None, f"({text})"
    return None, text


def _search_compare_text(tree) -> str:
    """One compared search: a phrase or word bare, anything else in parentheses."""
    t = _search_item_text(tree)
    single = (t.startswith('"') and t.endswith('"') and t.count('"') == 2) or " " not in t
    return t if single else f"({t})"


def compare_text(splits: List[GroupBy], entity: str, noun: str, resolver=None,
                 measures: Optional[str] = None) -> str:
    """`institution [MIT](I63966007) versus [Stanford University](I97018004) using count
    by year`: the measures right after the things compared, the breakdowns last."""
    g = splits[0]
    if g.conditions is not None:
        parts, prev = [], None
        for c in g.conditions:
            f, rest = _compare_item(c, resolver)
            parts.append(rest if f is not None and f == prev
                         else (f"{f} {rest}" if f else rest))
            prev = f
        text = " versus ".join(parts)
    else:
        name = L._oql_field(g.column_id)[0]
        if g.column_id.endswith(".search"):
            items = [_search_compare_text(v) for v in g.values]
            text = f"{name} has " + " versus ".join(items)
        elif len(g.values) == 1 and str(g.values[0]).startswith("col_"):
            text = (f"each {name} in the collection "
                    f"{link_text(g.values[0], 'collections', resolver)}")
        else:
            items = []
            for v in g.values:
                vsegs, _ent = L._value_segments(L._BY_COLUMN.get(g.column_id), v,
                                                g.column_id, resolver)
                items.append(_segs_text(_links(vsegs, in_list=False)))
            text = f"{name} " + " versus ".join(items)
    bys = []
    for b in splits[1:]:
        _prefix, segs = _split_segments(b, noun, again=False, resolver=resolver)
        t = "by " + _segs_text(segs)
        if b.where is not None:
            from query_translation.oql_lang import _group_entity, _singular_noun
            ge = _group_entity(b, entity)
            ctx = {"noun": noun, "group_entity": ge,
                   "singular": _singular_noun(ge) if ge else None}
            t += " where " + _group_where_text(b.where, ctx, resolver)
        bys.append(t)
    out = text if measures is None else f"{text} using {measures}"
    for i, t in enumerate(bys):
        if i == 0:
            out += " " + t
        elif splits[i].where is not None or splits[i].bins is not None \
                or splits[i + 1].bins is not None:   # `and by` after a filter or bins
            out += " and " + t
        elif len(bys) >= 3 and all(b.where is None and b.bins is None for b in splits[1:]):
            out += (", and " if i == len(bys) - 1 else ", ") + t[len("by "):]
        else:                                  # `by year and type`
            out += " and " + t[len("by "):]
    return out


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


# ---------------------------------------------------------------------------
# Thing-first (oxjob #1555, Jason 2026-10-09): every split by a thing reads
# `get authors at [UBC](I141945490) since 2022 who published works where ...`
# ---------------------------------------------------------------------------
# After `at [UBC] since 2022`, words that say the works may come from anywhere (pending
# Jason's call on the reading test; accepted on input either way)
ANY_WORKS = ""

_COUNT_WORDS = {">": "more than", ">=": "at least", "<": "fewer than", "<=": "at most"}
_PLACE_COLUMNS = {
    # author's record: (word, when)
    # `at [X] now` reads as the field it is, `last known institution is [X]`: our guess
    # from the same record, not foregrounded (Jason 2026-10-09 18:27 CT)
    "affiliations.institution.lineage": ("at", "ever"),
    "affiliations.institution.country_code": ("in", "ever"),
}
_OWN_PLACE_COLUMNS = {"country_code", "continent", "country_codes"}


# where a thing-first start's verb sits (`who published [more than 5] works`)
_THING_VERB_AT = re.compile(r" (?:%s) (?=(?:(?:%s) )?\d* ?works\b)" % (
    "|".join(sorted(set(L.THING_VERBS.values()))), "|".join(_COUNT_WORDS.values())))


def thing_first(oqo: OQO) -> Optional[Tuple[str, bool]]:
    """(the thing, whole set?) when the echo starts with the thing: a works query whose
    first split is by a thing (one row each), or a walk to the things' combined set
    that is summarized (`then, summarize all those authors using ...`)."""
    if oqo.get_rows != "works" or oqo.each or oqo.sample:
        return None
    if oqo.walks:
        w = oqo.walks[0]
        if (len(oqo.walks) == 1 and w.to is None and not w.each and not oqo.group_by
                and oqo.calculate and w.column_id in L.THING_BY_COLUMN
                and not L._has_measure_filter(w.where)):
            return L.THING_BY_COLUMN[w.column_id], True
        return None
    if not oqo.group_by:
        return None
    g = oqo.group_by[0]
    if g.values is not None or g.bins is not None or g.conditions is not None:
        return None
    ent = L.THING_BY_COLUMN.get(g.column_id)
    if ent is None or not _head_says(g.where):
        return None
    return ent, False


def _head_says(where) -> bool:
    """Can the thing-first start say this filter? Every calculation but one count is
    the old split's (`group those works by author where mean FWCI of those works is at
    least 2`): `keep` is gone (Jason 2026-10-09 18:37 CT: "Drop it")."""
    measures = [p for p in _and_parts(where) if L._has_measure_filter(p)]
    return not measures or (len(measures) == 1 and _count_in_head(measures[0]))


def _count_in_head(m) -> bool:
    """`who published more than 5 works where ...`"""
    return (isinstance(m, MeasureFilter) and m.measure == "count" and not m.is_negated
            and m.operator in _COUNT_WORDS)


def _and_parts(node) -> List:
    if node is None:
        return []
    if isinstance(node, BranchFilter) and node.join == "and" and not node.is_negated:
        return list(node.filters)
    return [node]


def _place_leaves(node, thing: str) -> Optional[List]:
    """The leaves of a place part (`at [UBC] since 2022`, `at ([A] or [B]) now`, `in
    [Asia]`): one kind, one set of years, all positive, joined by `or`; else None."""
    leaves = [node] if not isinstance(node, BranchFilter) else (
        node.filters if node.join == "or" and not node.is_negated else [])
    if not leaves:
        return None
    kinds = set()
    for x in leaves:
        if isinstance(x, AffiliationFilter) and not x.is_negated and thing == "authors":
            kinds.add((x.column_id, x.since, x.through, x.min_years))
        elif (isinstance(x, LeafFilter) and not x.is_negated and x.operator == "is"
              and not isinstance(x.value, OQO)
              and ((thing == "authors" and x.column_id in _PLACE_COLUMNS)
                   or (thing != "authors" and x.column_id in _OWN_PLACE_COLUMNS))):
            kinds.add((x.column_id,))
        else:
            return None
    return leaves if len(kinds) == 1 else None


def _years_text(since, through) -> str:
    if since is not None and through is not None:
        return f"in {since}" if since == through else f"from {since} through {through}"
    if since is not None:
        return f"since {since}"
    if through is not None:
        return f"through {through}"
    return ""


def _place_text(leaves: List, resolver=None) -> str:
    x = leaves[0]
    col = x.column_id
    if isinstance(x, AffiliationFilter):
        word, when = ("in" if col.endswith("country_code") else "at"), _years_text(x.since, x.through)
    elif col in _PLACE_COLUMNS:
        word, when = _PLACE_COLUMNS[col]
    else:
        word, when = "in", ""
    ns = ("countries" if "country" in col else "continents" if col == "continent"
          else "institutions")
    vals = [link_text(v.value, ns, resolver, in_list=len(leaves) > 1) for v in leaves]
    vals_text = vals[0] if len(vals) == 1 else "(" + " or ".join(vals) + ")"
    if isinstance(x, AffiliationFilter):
        # `at [UBC] in 2+ years since 2022`; no years at all reads `ever at`
        lead = "" if when else "ever "
        mid = f" in {x.min_years}+ years" if x.min_years else ""
        return f"{lead}{word} {vals_text}{mid}" + (f" {when}" if when else "")
    if when == "ever":
        return f"ever {word} {vals_text}"
    return f"{word} {vals_text}" + (f" {when}" if when else "")


def _thing_head(where, thing: str, resolver=None) -> str:
    """The start up to `works` for a thing's own conditions: places first, then `where
    <own fields>`, the verb, a count (`thing_first` checked the head can say them)."""
    from query_translation.walks import plural, singular
    places, own, measures = [], [], []
    for p in _and_parts(where):
        leaves = _place_leaves(p, thing)
        if leaves is not None:
            places.append(leaves)
        elif isinstance(p, LeafFilter) and p.column_id == "collection":
            places.append(p)          # `not in the collection [Our lab](col_x)`
        elif L._has_measure_filter(p):
            measures.append(p)
        else:
            own.append(p)
    count = measures[0] if measures else None
    ctx = {"noun": "works", "group_entity": thing, "singular": singular(thing)}
    head = f"get {plural(thing)}"
    for leaves in places:
        if isinstance(leaves, LeafFilter):
            head += (" not" if leaves.is_negated else "") + " in the collection " + \
                link_text(leaves.value, "collections", resolver)
            continue
        head += " " + _place_text(leaves, resolver)
    if own:
        tree = own[0] if len(own) == 1 else BranchFilter("and", own)
        head += " where " + _group_where_text(tree, ctx, resolver)
    head += f" {L.THING_VERBS[thing]} "
    if count is not None:
        head += f"{_COUNT_WORDS[count.operator]} {_number(count.value)} "
    head += "works"
    if places and ANY_WORKS:
        head += f" {ANY_WORKS}"
    return head


def _build_thing_first(oqo: OQO, thing: str, whole_set: bool, resolver=None) -> OQLRenderTree:
    from query_translation.walks import plural, singular
    where = oqo.walks[0].where if whole_set else oqo.group_by[0].where
    head_text = _thing_head(where, thing, resolver)
    head = EntityHead(id="works", text=head_text)
    where_keyword, wnode = "", None
    if oqo.filter_rows:
        where_keyword = " where "
        wnode = where_node(list(oqo.filter_rows), resolver, top=True)
    steps: List[StepDirective] = []
    rest = [] if whole_set else oqo.group_by[1:]
    if rest:
        # each thing's works split further: `group each institution's works by year`
        sub = replace(oqo, group_by=rest, calculate=[])
        n0 = len(steps)
        _later_steps(sub, steps, "works", "works", resolver)
        first = steps[n0]
        first.prefix = first.prefix.replace("group those works by ",
                                            f"group each {singular(thing)}'s works by ", 1)
        for d in steps[n0:]:
            if d.meta.index is not None:
                d.meta.index += 1
    if oqo.calculate:
        if whole_set:
            prefix = f"summarize all those {plural(thing)} using "
        elif rest:
            prefix = SUMMARIZE
        else:
            prefix = f"summarize each {singular(thing)} using "
        steps.append(_summary_step(oqo, prefix, "works"))
    for d, word in zip(steps, transitions(len(steps))):
        d.joiner = f"; {word}, "
    return OQLRenderTree(version="1.0", entity=head, where_keyword=where_keyword,
                         where=wnode, directives=steps, corpus_phrase=_corpus_phrase(oqo))


def _corpus_phrase(oqo: OQO) -> str:
    if getattr(oqo, "corpus", "core") and oqo.corpus != "core":
        return f" ({L.CORPUS_CANONICAL_PHRASE.get(oqo.corpus, oqo.corpus)})"
    return ""


def _summary_prefix(oqo: OQO) -> str:
    """The summary names what it summarizes (Jason 2026-10-09): `summarize all those
    works using`, `summarize all those authors using`, `summarize each author using`
    (one row per thing); after a split, `summarize using` (the split says per what)."""
    from query_translation.walks import entity_for_link, singular
    if oqo.group_by:
        return SUMMARIZE
    cur, each = oqo.get_rows, bool(oqo.each)
    for w in oqo.walks:
        if w.to is None:
            cur, each = entity_for_link(w.column_id) or "works", w.each
        elif not each:
            cur = w.to
    if each:
        # one row per thing: `get each author ...` (with or without the walk back)
        return f"summarize each {singular(cur)} using "
    return f"summarize all those {L._plural_noun(cur)} using "


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
    tf = thing_first(oqo)
    if tf is not None:
        return _build_thing_first(oqo, *tf, resolver=resolver)
    entity = oqo.get_rows
    noun = L._plural_noun(entity)
    head_text = f"get {entity.lower()}"
    filters = list(oqo.filter_rows)
    start_list = (entity == "works" and not oqo.each and filters
                  and getattr(filters[0], "column_id", None) == "ids.openalex"
                  and str((_start_ids(filters[0]) or [""])[0]).startswith("col_"))
    if start_list:
        # `get works in [My list](col_x)`: a saved list of works (oxjob #1555)
        head_text = (f"get works in the collection "
                     f"{link_text(_start_ids(filters[0])[0], 'collections', resolver)}")
        filters = filters[1:]
    if oqo.each:
        # `get each institution in (I1, I2)` (oxjob #1535)
        head_text = f"get each {singular(entity)}"
        ids = _start_ids(filters[0]) if filters else None
        if ids is not None:
            ns = "collections" if str(ids[0]).startswith("col_") else entity
            items = [link_text(v, ns, resolver, in_list=len(ids) > 1) for v in ids]
            head_text += (" in the collection " + items[0] if ns == "collections"
                          else " in " + items[0] if len(ids) == 1
                          else " in (" + ", ".join(items) + ")")
            filters = filters[1:]
    head = EntityHead(id=entity, text=head_text)
    where_keyword, where = "", None
    if filters:
        where_keyword = " where "
        where = where_node(filters, resolver, top=True)

    steps: List[StepDirective] = []
    if oqo.sample:
        segs = [L._seg("value", f"{oqo.sample}", value=oqo.sample),
                _text(f" of those {noun}")]
        if oqo.seed is not None:
            segs.append(_text(f" with seed {oqo.seed}"))
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
                         where=where, directives=steps, corpus_phrase=_corpus_phrase(oqo))


def _later_steps(oqo: OQO, steps: List[StepDirective], entity: str, noun: str,
                 resolver=None):
    """The splits and the calculation."""
    if oqo.group_by and is_compare_split(oqo.group_by[0]):
        # `compare institution [MIT] versus [Stanford] using count by year` (oxjob
        # #1555, Jason 2026-10-08): the measures inside the step, as in `summarize using`
        measures = (english_list([measure_text(m, noun) for m in oqo.calculate])
                    if oqo.calculate else None)
        data = {"splits": [g.to_dict() for g in oqo.group_by]}
        if oqo.calculate:
            data["measures"] = [dict(m.to_dict(), key=m.key) for m in oqo.calculate]
        steps.append(StepDirective(
            prefix="compare ", segments=[_text(compare_text(oqo.group_by, entity, noun,
                                                            resolver, measures))],
            meta=StepMeta("compare", index=0, data=data)))
        return
    # `group those works by author and year` (Jason 2026-10-08): every split in one
    # step, joined `and`; `and by` after a group filter, so the next split can't read
    # as part of the condition. A listed set of conditions keeps its own step.
    cur = None
    plain_run = (len(oqo.group_by) >= 3 and all(
        g.where is None and g.bins is None and g.conditions is None for g in oqo.group_by))
    for i, g in enumerate(oqo.group_by):
        prefix, segs = _split_segments(g, noun, again=cur is not None, resolver=resolver)
        if cur is not None and g.bins is not None:
            segs = [_text("by ")] + segs      # `... and by citation count bins at (...)`
        if g.where is not None:
            from query_translation.oql_lang import _group_entity, _singular_noun
            ge = _group_entity(g, entity)
            ctx = {"noun": noun, "group_entity": ge,
                   "singular": _singular_noun(ge) if ge else None}
            segs = segs + [_text(" where " + _group_where_text(g.where, ctx, resolver))]
        if cur is not None and g.conditions is None:
            prev = oqo.group_by[i - 1]
            if plain_run:   # `by year, type, and country` (the Oxford comma, as in lists)
                joiner = ", and " if i == len(oqo.group_by) - 1 else ", "
            elif g.bins is not None:
                joiner = " and "
            elif prev.where is not None or prev.bins is not None:
                joiner = " and by "
            else:
                joiner = " and "
            cur.segments = cur.segments + [_text(joiner)] + segs
            cur.meta.data.setdefault("splits", [oqo.group_by[cur.meta.index].to_dict()])
            cur.meta.data["splits"].append(g.to_dict())
            continue
        cur = StepDirective(prefix=prefix, segments=segs,
                            meta=StepMeta("split", index=i, data=g.to_dict()))
        steps.append(cur)
    if oqo.calculate:
        steps.append(_summary_step(oqo, _summary_prefix(oqo), noun))


def _summary_step(oqo: OQO, prefix: str, noun: str) -> StepDirective:
    """`summarize ... using <measures>`: the calculation's step."""
    return StepDirective(
        prefix=prefix,
        segments=[_text(english_list([measure_text(m, noun) for m in oqo.calculate]))],
        meta=StepMeta("calculate", data={
            "measures": [dict(m.to_dict(), key=m.key) for m in oqo.calculate]}))


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
    m = _THING_VERB_AT.search(tree.entity.text)
    if m is not None and len(tree.entity.text[:m.start()].split()) > 2:
        # a long thing-first start breaks before its verb (oxjob #1555):
        #   get authors where h-index is above 20
        #     who published more than 10 works where title-abstract has kelp
        text = tree.entity.text
        head = (text[:m.start()] + "\n" + " " * L._INDENT + text[m.start() + 1:]
                + tree.corpus_phrase + tree.where_keyword)
    if tree.where is not None:
        col = len(head) - head.rfind("\n") - 1
        head += L._fmt_expr(tree.where, L._INDENT, col, width)
    lines = [head]
    for d in tree.directives:
        lines[-1] += ";"
        line = f"{d.joiner[2:]}{d.prefix}{_segs_text(d.segments)}"
        wrap = _wrap_compare if d.meta.step == "compare" else _wrap_step
        lines.extend(wrap(line, width))
    return "\n".join(lines)


def _top_level(text: str, needles) -> List[int]:
    """Where each needle starts outside quotes, parentheses and a link's brackets."""
    out, depth, quoted, j = [], 0, False, 0
    while j < len(text):
        c = text[j]
        if c == '"':
            quoted = not quoted
        elif not quoted and c in "([":
            depth += 1
        elif not quoted and c in ")]":
            depth -= 1
        elif not quoted and depth == 0 and any(text.startswith(n, j) for n in needles):
            out.append(j)
        j += 1
    return out


def _wrap_compare(line: str, width: int) -> List[str]:
    """A comparison over the width: `  using ...` and `  by ...` on their own lines;
    the things compared one per line (`  versus ...`) when they still don't fit."""
    if len(line) <= width:
        return [line]
    cuts = _top_level(line, (" using ",))[:1] + _top_level(line, (" by ",))[:1]
    cuts = sorted(cuts)
    pieces = [line[i:j] for i, j in zip([0] + cuts, cuts + [len(line)])]
    items, rest = pieces[0], [p.strip() for p in pieces[1:]]
    out = [items]
    if len(items) > width:
        vs = _top_level(items, (" versus ",))
        out = [items[i:j].strip() for i, j in zip([0] + vs, vs + [len(items)])]
        out = [out[0]] + [f"  {p}" for p in out[1:]]
    return out + [f"  {p}" for p in rest]


def _wrap_step(line: str, width: int) -> List[str]:
    """A step over the width: its group filter on the next lines, one condition
    per line (`  where ...` / `  and ...`), split only at top-level connectives."""
    if len(line) <= width:
        return [line]
    m = re.match(r"((?:then|finally|first|next), summarize (?:each \S+|all those [^ ]+(?: [^ ]+)??) )"
                 r"(using .*)$", line)
    if m is not None:
        # `then, summarize all those works` / `  using count, mean FWCI, ...` (oxjob #1555)
        return [m.group(1).rstrip(), "  " + m.group(2)]
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
        elif not quoted and c == "[":
            depth += 1      # a link's name: `[Marine and coastal ecosystems](T10032)`
        elif not quoted and c == "]":
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


def set_phrase(oqo: OQO, resolver=None) -> Optional[str]:
    """A query in a set's parentheses as a phrase (oxjob #1555, Jason 2026-10-08: no
    `get`, no article): `works where X`, `authors of works where X`, `works of authors
    where X`. None when the query is more than a filter and plain walks (a walk with
    its own `where`, `each`, a sample): it's written out whole then."""
    from query_translation.walks import entity_for_link, plural
    if oqo.sample or oqo.group_by or oqo.calculate or oqo.each:
        return None
    head = render_pipeline_line(replace(oqo, walks=[]), resolver)
    if not head.startswith("get ") or "; " in head:
        return None
    phrase = head[len("get "):]
    for w in oqo.walks:
        if w.where is not None or w.each:
            return None
        if w.to is None:
            ent = entity_for_link(w.column_id)
            if ent is None:
                return None
            phrase = f"{plural(ent)} of {phrase}"
        elif w.to == "works":
            phrase = f"works of {phrase}"
        else:
            return None
    return phrase


def render_pipeline_line(oqo: OQO, resolver=None) -> str:
    """The canonical text on one line (a query inside another's parentheses)."""
    return stringify_pipeline(build_pipeline_tree(oqo, resolver))
