"""
OQO (OpenAlex Query Object) Data Model

The canonical JSON representation for query format translation.
All translations go through OQO as the intermediate format.
"""

from dataclasses import dataclass, field, replace
from typing import List, Optional, Union, Literal, Any, Dict

# Smart/curly DOUBLE-quote characters coerced to a plain ASCII double-quote
# wherever a string delimiter is expected — left/right double quotation marks +
# the double low-9 / high-reversed-9 forms. (oxjob #363; the single curly quotes
# 2018/2019 are NOT included — they're apostrophes in real text, never string
# delimiters.) Single source of truth for both surfaces that coerce quotes: the
# OQL lexer (position-preserving) and the URL value parser.
CURLY_DQUOTE_MAP = {ord(c): '"' for c in "“”„‟"}


@dataclass
class LeafFilter:
    """A single filter condition (a literal = atom + polarity).

    `value` is a *bare* scalar — the namespace/type is carried by `column_id`
    (resolved via the column registry), NOT by a prefix on the value. So an
    institution reference is `"I136199984"`, a country is `"de"`, a type is
    `"article"`, an SDG is `"13"` — never `"institutions/I136199984"` etc.

    Negation is the `is_negated` polarity bit, never an operator: there is one
    negation mechanism. (The old `is not` / `does not have` operators are
    removed; see VALID_OPERATORS.)
    """
    column_id: str
    # A value may also be a whole query (a nested OQO, oxjob #1535): `author is in
    # (get works where ...; then get authors of those works)`, `it cites works in
    # (get works where ...)`. Its result type must match the column's entity.
    value: Union[str, int, bool, None, "OQO"]
    operator: str = "is"
    is_negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "column_id": self.column_id,
            # a nested query, or a set resolved while running (walk_exec.IdSet)
            "value": (self.value.to_dict() if hasattr(self.value, "to_dict")
                      else self.value),
        }
        if self.operator != "is":
            result["operator"] = self.operator
        if self.is_negated:
            result["is_negated"] = True
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeafFilter":
        value = data["value"]
        if isinstance(value, dict) and "get_rows" in value:
            value = OQO.from_dict(value)
        return cls(
            column_id=data["column_id"],
            value=value,
            operator=data.get("operator", "is"),
            is_negated=data.get("is_negated", False),
        )


@dataclass
class BranchFilter:
    """A boolean combination of filters.

    `is_negated` negates the whole branch (semantically a unary NOT node). The
    canonicalizer pushes branch-level negation down to the leaves via De Morgan
    (NNF), so a *canonical* OQO carries `is_negated` only on leaves.
    """
    join: Literal["and", "or"]
    filters: List[Union["LeafFilter", "BranchFilter"]]
    is_negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "join": self.join,
            "filters": [f.to_dict() for f in self.filters],
        }
        if self.is_negated:
            result["is_negated"] = True
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BranchFilter":
        filters = [filter_from_dict(f) for f in data["filters"]]
        return cls(join=data["join"], filters=filters,
                   is_negated=data.get("is_negated", False))


@dataclass
class MeasureFilter:
    """A group-filter condition on a calculated measure of the group's works
    (oxjob #1530): `count of those works > (10)`, `mean FWCI of those works >= (2)`.

    Only valid inside a `GroupBy.where` tree, beside ordinary leaves on the group's
    own fields. `measure` is one of MEASURES; `column_id` names the measured column
    (None for `count`)."""
    measure: str
    operator: str
    value: Union[int, float]
    column_id: Optional[str] = None
    is_negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result = {"measure": self.measure}
        if self.column_id is not None:
            result["column_id"] = self.column_id
        result["operator"] = self.operator
        result["value"] = self.value
        if self.is_negated:
            result["is_negated"] = True
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeasureFilter":
        return cls(
            measure=data["measure"],
            operator=data.get("operator", ">"),
            value=data["value"],
            column_id=data.get("column_id"),
            is_negated=data.get("is_negated", False),
        )


FilterType = Union[LeafFilter, BranchFilter]


def filter_from_dict(data: Dict[str, Any]) -> FilterType:
    """Convert a dict to a LeafFilter, BranchFilter or (group filters only) MeasureFilter."""
    if "join" in data:
        return BranchFilter.from_dict(data)
    if "measure" in data:
        return MeasureFilter.from_dict(data)
    return LeafFilter.from_dict(data)


def _is_xpac_value_truthy(value) -> bool:
    """Interpret an `is_xpac` filter leaf value as a boolean. Accepts the parsed
    string forms (`"true"`/`"false"`) the URL/OQL parsers produce, a real bool, or
    any other value (treated by Python truthiness; `None`/`"false"` → False)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def redirect_is_xpac_to_corpus(oqo: "OQO") -> "OQO":
    """Soft-retire the legacy `is_xpac` works filter (#498): fold a TOP-LEVEL
    `is_xpac` leaf into the first-class `corpus` selector (#481).

        is_xpac:true   → corpus="expansion"   (the expansion corpus alone)
        is_xpac:false  → corpus="core"          (the curated corpus)
        !is_xpac:true  ≡ is_xpac:false → core
        !is_xpac:false ≡ is_xpac:true  → expansion

    Why: #481 made `corpus` the first-class way to pick core/expansion/all, which
    makes the user-facing `is_xpac` filter redundant. This redirect keeps every
    OQO/OQL/oxurl caller that still names `is_xpac` working, while the CANONICAL
    OQO carries `corpus` (so it renders + round-trips as the corpus selector and
    never re-emits the deprecated filter).

    Scope:
      * works queries only (`corpus` is works-only); other entities pass through.
      * TOP-LEVEL leaves only. A nested `is_xpac` inside an OR/AND branch is NOT a
        corpus *selection* (you can't OR a base-corpus choice), so it's left as a
        plain ES term filter — the column survives internally (it stays a live,
        UNLISTED works field; see works/fields.py). The executor's
        `_oqo_mentions_column(..., "is_xpac")` escape-hatch still suppresses corpus
        injection for that exotic case, so behavior is unchanged.

    Last top-level `is_xpac` leaf wins, and the derived corpus OVERRIDES any
    pre-existing `corpus` — mirroring the legacy "an explicit is_xpac filter is the
    escape hatch that wins" precedence (query_translation/execution.py). Pure +
    idempotent (a second pass finds no `is_xpac` leaf and is a no-op)."""
    if oqo.get_rows != "works":
        return oqo
    if not any(
        isinstance(f, LeafFilter) and f.column_id == "is_xpac"
        for f in oqo.filter_rows
    ):
        return oqo
    corpus = oqo.corpus
    kept = []
    for f in oqo.filter_rows:
        if isinstance(f, LeafFilter) and f.column_id == "is_xpac":
            truthy = _is_xpac_value_truthy(f.value)
            if f.is_negated:
                truthy = not truthy
            corpus = "expansion" if truthy else "core"
            continue  # drop the redirected leaf
        kept.append(f)
    return replace(oqo, corpus=corpus, filter_rows=kept)


def canonicalize_oqo_column_ids(oqo: "OQO") -> "OQO":
    """Return a COPY of `oqo` with every FILTER-namespace `column_id` mapped to its
    single CANONICAL identity for the entity (#455): filter leaves (recursively
    through branches), `sort_by`, and `group_by`. An alias spelling (`is_oa`,
    `institution.id`, `cites`, `journal`) collapses to its canonical
    (`open_access.is_oa`, `authorships.institutions.id`, `referenced_works`,
    `primary_location.source.id`) so every downstream consumer — validator,
    canonicalizer/cache key, render, ES translation — sees ONE spelling.

    `select` is INTENTIONALLY NOT canonicalized here. The column/`select` capability
    is a SEPARATE namespace from filter/sort/group (#450): its values are the
    result-field names the executor projects (`id`, `display_name`, `cited_by_count`),
    which are mostly disjoint from the filter namespace and have their OWN identity
    rules. The #446 `alternate_of` map encodes the *filter*-namespace identity — e.g.
    on authors `id`'s `alternate_of` is the filter key `ids.openalex`, which is NOT a
    valid `?select=` column. Applying it to `select` would corrupt projection, so
    column-namespace canonicalization is deferred to the friendly-name/display_name
    work (Phase B/C), which needs a column-namespace alias map.

    Applied at each OQO-construction boundary (OQL parse, URL parse, `from_dict`)
    and again in the canonicalizer; **idempotent** and pure (never mutates the input
    — `replace` builds new nodes), so the execution OQO and any render copy stay
    decoupled. Aliases are accepted on input and rewritten here, never rejected.
    Synthetic sort keys (`relevance_score`/`count`/`key`) and unknown columns pass
    through unchanged (the validator still gates the latter). A no-op when
    `core.properties` can't be imported (degrade to the raw spellings rather than
    crash a parse).

    Also folds the deprecated `is_xpac` works filter into the `corpus` selector
    (#498) — done FIRST and import-independently, so the redirect runs on every
    construction boundary even if the column-id canonicalization below degrades."""
    oqo = redirect_is_xpac_to_corpus(oqo)
    try:
        from core.properties import canonicalize_column_id
    except Exception:
        return oqo
    start = oqo.get_rows
    # splits, calculations and sorts belong to the things the query holds at the
    # end: after a walk, the walk's (oxjob #1535)
    entity = result_entity(oqo)

    def _canon(column_id):
        return canonicalize_column_id(column_id, entity)

    def _canon_filter(f, ent=start):
        if isinstance(f, BranchFilter):
            return replace(f, filters=[_canon_filter(x, ent) for x in f.filters])
        if f.column_id is None:
            return f
        if isinstance(f, MeasureFilter):  # measured column is a column of the main entity
            return replace(f, column_id=_canon(f.column_id))
        if isinstance(f.value, OQO):  # a nested query (oxjob #1535)
            return replace(f, column_id=canonicalize_column_id(f.column_id, ent),
                           value=canonicalize_oqo_column_ids(f.value))
        return replace(f, column_id=canonicalize_column_id(f.column_id, ent))

    def _canon_walk(w):
        # a walk out's link is a works column and its `where` sits in the walked
        # entity's namespace; a walk back's `where` in works' (oxjob #1535)
        if w.to is not None:
            return replace(w, where=_canon_filter(w.where, w.to) if w.where is not None else None)
        column_id = canonicalize_column_id(w.column_id, "works")
        where = w.where
        if where is not None:
            where = _canon_filter(where, walked_entity(column_id) or "works")
        return replace(w, column_id=column_id, where=where)

    def _canon_group(g):
        if g.is_plain:
            return replace(g, column_id=_canon(g.column_id))
        column_id = _canon(g.column_id) if g.column_id is not None else None
        values = g.values
        if values is not None:
            values = [_canon_filter(v) if isinstance(v, (LeafFilter, BranchFilter)) else v
                      for v in values]
        conditions = g.conditions
        if conditions is not None:
            conditions = [_canon_filter(c) for c in conditions]
        where = g.where
        if where is not None:
            # Own-field leaves live in the GROUP entity's namespace (an author's
            # h-index), measure leaves in the main one.
            group_entity = None
            if column_id is not None:
                try:
                    from query_translation.oql_lang import entity_type_for_column
                    group_entity = entity_type_for_column(column_id, entity)
                except Exception:
                    group_entity = None
            where = _canon_filter(where, group_entity or entity)
        return replace(g, column_id=column_id, values=values, conditions=conditions, where=where)

    return replace(
        oqo,
        filter_rows=[_canon_filter(f) for f in oqo.filter_rows],
        walks=[_canon_walk(w) for w in oqo.walks],
        sort_by=[replace(s, column_id=_canon(s.column_id)) for s in oqo.sort_by],
        group_by=[_canon_group(g) for g in oqo.group_by],
        calculate=[replace(m, column_id=_canon(m.column_id)) if m.column_id else m
                   for m in oqo.calculate],
    )


@dataclass
class Walk:
    """One walk step of the pipeline language (oxjob #1535). `walks` on the OQO is
    the ordered list, between the start (`filter_rows`, `sample`) and the splits.

    * A walk out, from works to the things they relate to: `column_id` is the works
      column that links them, the one the noun means in a filter (`author` is
      `authorships.author.id`); `each` gives one result per thing (`get each author
      of those works`), else one combined set (`get authors of those works`, so
      `summarize using count` counts distinct authors).
    * A walk back, from the things to everything they did: `to: "works"` (`get all
      that author's works`, or `get all those authors' works` after a set). It
      follows the walk out's column, or after a non-works start that entity's
      link.

    `where` filters the new current things by their own fields (an author's
    h-index; the works' date)."""
    column_id: Optional[str] = None
    to: Optional[str] = None
    each: bool = False
    where: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.to is not None:
            d["to"] = self.to
        else:
            d["column_id"] = self.column_id
            d["each"] = bool(self.each)
        if self.where is not None:
            d["where"] = self.where.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Walk":
        where = data.get("where")
        return cls(column_id=data.get("column_id"), to=data.get("to"),
                   each=bool(data.get("each", False)),
                   where=filter_from_dict(where) if where is not None else None)


def walked_entity(column_id: Optional[str]) -> Optional[str]:
    """The entity a works column links to (`authorships.author.id` -> authors)."""
    from query_translation.walks import entity_for_link
    return entity_for_link(column_id)


def result_entity(oqo: "OQO") -> str:
    """What the query holds after its walks (oxjob #1535): the last walk's things,
    else what it started with."""
    if not oqo.walks:
        return oqo.get_rows
    last = oqo.walks[-1]
    return last.to if last.to is not None else (walked_entity(last.column_id) or oqo.get_rows)


def has_query_value(node) -> bool:
    """True when a filter tree holds a nested query as a value (oxjob #1535)."""
    if isinstance(node, BranchFilter):
        return any(has_query_value(f) for f in node.filters)
    return isinstance(node, LeafFilter) and isinstance(node.value, OQO)


# Co-occurrence relations: group filters in #1530, top-level filters since #1535
# (`get authors where co-author is (A1)`). They resolve to ids when the query runs.
RELATION_COLUMNS = {"co_author": "authors", "collaborator": "institutions"}


def has_relation_leaf(node) -> bool:
    if isinstance(node, BranchFilter):
        return any(has_relation_leaf(f) for f in node.filters)
    return isinstance(node, LeafFilter) and node.column_id in RELATION_COLUMNS


@dataclass
class GroupBy:
    """One split (group-by dimension). `group_by` on the OQO is the ordered list of
    splits, outermost first (up to three).

    The plain split is just `column_id`. The pipeline language (oxjob #1530) adds,
    at most one of `values` / `bins` / `conditions` per split:
      * `values`: split only by these values of `column_id`, one group each — bare
        ids (`["I63966007", ...]`), or, for a search column, one filter tree per
        search (`title-abstract search in (("a"), ("b" NOT c))`);
      * `bins`: `{"at": [edges]}` or `{"of": width}` on a numeric column;
      * `conditions`: one filter tree per group (`into ((...), (...))`); no column.
    and `where`, the group filter: a tree of MeasureFilter leaves (calculations on
    the group's works) and ordinary leaves on the group entity's own fields.
    """
    column_id: Optional[str] = None
    values: Optional[List[Any]] = None
    bins: Optional[Dict[str, Any]] = None
    conditions: Optional[List[Any]] = None
    where: Optional[Any] = None

    @property
    def is_plain(self) -> bool:
        """True for today's split (a column, nothing else)."""
        return (self.values is None and self.bins is None
                and self.conditions is None and self.where is None)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.column_id is not None:
            d["column_id"] = self.column_id
        if self.values is not None:
            d["values"] = [v.to_dict() if hasattr(v, "to_dict") else v for v in self.values]
        if self.bins is not None:
            d["bins"] = dict(self.bins)
        if self.conditions is not None:
            d["conditions"] = [c.to_dict() for c in self.conditions]
        if self.where is not None:
            d["where"] = self.where.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupBy":
        values = data.get("values")
        if values is not None:
            values = [filter_from_dict(v) if isinstance(v, dict) else v for v in values]
        conditions = data.get("conditions")
        if conditions is not None:
            conditions = [filter_from_dict(c) for c in conditions]
        where = data.get("where")
        return cls(
            column_id=data.get("column_id"),
            values=values,
            bins=dict(data["bins"]) if data.get("bins") is not None else None,
            conditions=conditions,
            where=filter_from_dict(where) if where is not None else None,
        )


# Calculations (oxjob #1530). `percent_of_those` is the group's share of the set it
# came from (`percent of those works`); `percent` takes a yes/no column; the rest a
# numeric column (min / max also a date); `count` none. `value` is a split's own
# field shown beside each group (`summarize using count, h-index` after a split by author):
# not computed from the works but read from the group's own record.
MEASURES = ("count", "mean", "median", "sum", "min", "max", "percent", "percent_of_those",
            "value")
NUMERIC_MEASURES = ("mean", "median", "sum", "min", "max")


@dataclass
class Measure:
    """One measure in the final `summarize using` step: `count`, `mean FWCI`,
    `percent open access`, `percent of those works`."""
    measure: str
    column_id: Optional[str] = None

    @property
    def key(self) -> str:
        """The response key: `count`, `percent_of_those`, or `<measure>_<column>`
        with dots as underscores (`mean_fwci`, `percent_open_access_is_oa`), the
        convention of the #389 metric sort (`mean_cited_by_count`)."""
        if self.column_id is None:
            return self.measure
        if self.measure == "value":
            return self.column_id.replace('.', '_')
        return f"{self.measure}_{self.column_id.replace('.', '_')}"

    def to_dict(self) -> Dict[str, Any]:
        d = {"measure": self.measure}
        if self.column_id is not None:
            d["column_id"] = self.column_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Measure":
        return cls(measure=data["measure"], column_id=data.get("column_id"))


@dataclass
class SortBy:
    """A single sort key: a column plus a direction.

    `sort_by` on the OQO is an *ordered list* of these, so a multi-column sort
    (`sort=publication_year:desc,cited_by_count:desc`) is expressible: the list
    order is the tiebreaker priority (primary, secondary, …), applied in order
    by the legacy ES sort path (`core/sort.py:get_sort_fields`). Order is
    meaningful and is **preserved**, never sorted (unlike the commutative
    top-level `filter_rows`). `direction` defaults to `asc`, matching the legacy
    URL path's directionless-sort default (`core/utils.py:map_sort_params`).

    `column_id` may be a real entity column or a synthetic sort key:
    `relevance_score` (→ ES `_score`, desc-only, requires a search clause) or,
    when a `group_by` is present, the bucket-ordering keys `count` / `key`.

    `aggregate` (oxjob #389) is set ONLY for a metric-aggregate group sort: it
    orders the group_by buckets by a metric sub-aggregation of a numeric column
    (`mean`/`sum`/`min`/`max` of `column_id`), e.g. funders ranked by their works'
    mean citation impact. None ⇒ an ordinary row/bucket sort. The URL surface is
    the dotted pseudo-field `sort=<column_id>.<aggregate>:<direction>`
    (e.g. `cited_by_count.mean:desc`). Only meaningful with a group_by present.
    """
    column_id: str
    direction: Literal["asc", "desc"] = "asc"
    aggregate: Optional[Literal["mean", "sum", "min", "max"]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"column_id": self.column_id, "direction": self.direction}
        if self.aggregate is not None:
            d["aggregate"] = self.aggregate
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SortBy":
        return cls(
            column_id=data["column_id"],
            direction=data.get("direction", "asc"),
            aggregate=data.get("aggregate"),
        )


@dataclass
class OQO:
    """OpenAlex Query Object - the canonical query representation.

    Query/view split (#661): the PUBLIC OQO describes WHICH ROWS a query
    matches — `get_rows`, `corpus`, `filter_rows`, `group_by`, `sample`/`seed`
    — and nothing else. View/presentation parameters (`sort_by`, `select`,
    `per_page`/`page`/`cursor`) are NOT part of the public object (they're gone
    from docs/oqo-schema.json v1.4): they travel as SIBLING request params on
    the execute surface, classic URL syntax (`?sort=…&select=…&page=…`, or
    top-level POST-body keys). This dataclass still carries them as the
    INTERNAL execution struct — `_merge_view_params` (execution.py) folds the
    siblings in at the request boundary so the validator/canonicalizer/executor
    machinery is unchanged. `from_dict` also still accepts them embedded in an
    input dict as a TRANSITION (pre-#661 callers, i.e. today's GUI) — a sibling
    always wins over an embedded value; don't build new callers on that.
    """
    get_rows: str
    # `corpus` selects which corpus(es) seed the base result set — a
    # corpus-*selection* decision, distinct from a `filter` (which only narrows
    # an already-chosen corpus). Three states (#481):
    #   "core"      curated corpus only (default; engine injects is_xpac:false)
    #   "expansion" the expansion corpus ALONE — a distinct set, "more coverage,
    #               lower quality" (engine injects is_xpac:true). Subsumes the
    #               old `is_xpac` filter, which is now redirected here.
    #   "all"       core + expansion (engine applies no is_xpac constraint)
    # "core" is the back-compat default ⇒ absent behaves exactly as before.
    # ("xpac" is the internal engine term; user-facing language is core/expansion/all.)
    corpus: str = "core"
    filter_rows: List[FilterType] = field(default_factory=list)
    # `sort_by` is an ordered list of (column, direction) sort keys — the list
    # order is the tiebreaker priority. A multi-column sort URL round-trips
    # through this list; absent ⇒ the entity's implicit default sort applies.
    sort_by: List[SortBy] = field(default_factory=list)
    sample: Optional[int] = None
    group_by: List[GroupBy] = field(default_factory=list)
    # --- view layer (#318 "logistics"; INTERNAL since the #661 split) -----
    # sort_by (above) + select/per_page/page/cursor (below) are view state,
    # populated from sibling request params (or, transitionally, embedded
    # input-dict keys). Not in the public schema; still echoed in x_query
    # until the GUI stops rehydrating sort from it (#661 slice 2).
    # `select` is a list of registry column_ids carrying the `column`
    # capability (#450), e.g. ["id", "display_name", "cited_by_count"];
    # absent ⇒ full object. Order is meaningful (display order) and preserved.
    # These ids are string-identical to the MessageSchema result-field names
    # (the pre-#450 vocabulary), so older OQO dicts keep working unchanged.
    select: List[str] = field(default_factory=list)
    # `seed` makes a `sample` reproducible; only meaningful alongside `sample`.
    seed: Optional[Union[str, int]] = None
    # Pagination. `page` XOR `cursor`; absent both ⇒ page 1. `per_page` default
    # (25) / max (200) are applied at execution, not stored, so canonical OQOs
    # stay minimal and comparable.
    per_page: Optional[int] = None
    page: Optional[int] = None
    cursor: Optional[str] = None
    # The final `summarize using` step of the pipeline language (oxjob #1530): the
    # measures computed per group (and for the summary), or for the whole set
    # when there is no split. Part of WHICH ROWS a query returns, so public.
    calculate: List["Measure"] = field(default_factory=list)
    # Walks (oxjob #1535): `get each author of those works`, `get all that author's
    # works`; and `each` on a start that isn't works (`get each institution in
    # (...)`): one result per thing.
    walks: List[Walk] = field(default_factory=list)
    each: bool = False

    @property
    def uses_pipeline(self) -> bool:
        """True when the OQO uses anything only the pipeline language (oxjob
        #1530) can say: a calculation, a split beyond a plain column, a walk, or a
        nested query (oxjob #1535)."""
        return (bool(self.calculate) or any(not g.is_plain for g in self.group_by)
                or bool(self.walks) or self.each
                or any(has_query_value(f) or has_relation_leaf(f) for f in self.filter_rows))

    def to_dict(self) -> Dict[str, Any]:
        result = {"get_rows": self.get_rows}

        # Only emit non-default corpus so canonical OQOs stay minimal/comparable.
        if self.corpus and self.corpus != "core":
            result["corpus"] = self.corpus

        if self.filter_rows:
            result["filter_rows"] = [f.to_dict() for f in self.filter_rows]

        if self.sort_by:
            result["sort_by"] = [s.to_dict() for s in self.sort_by]

        if self.sample:
            result["sample"] = self.sample

        if self.each:
            result["each"] = True

        if self.walks:
            result["walks"] = [w.to_dict() for w in self.walks]

        if self.group_by:
            result["group_by"] = [g.to_dict() for g in self.group_by]

        if self.calculate:
            result["calculate"] = [m.to_dict() for m in self.calculate]

        if self.select:
            result["select"] = list(self.select)

        if self.seed is not None:
            result["seed"] = self.seed

        if self.per_page is not None:
            result["per_page"] = self.per_page

        if self.page is not None:
            result["page"] = self.page

        if self.cursor is not None:
            result["cursor"] = self.cursor

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OQO":
        filter_rows = [filter_from_dict(f) for f in data.get("filter_rows", [])]
        group_by = [GroupBy.from_dict(g) for g in data.get("group_by", [])]

        # `sort_by` is the canonical list shape. Back-compat: an OQO dict that
        # still carries the old scalar `sort_by_column` / `sort_by_order` keys
        # (pre-#333 fixtures / in-flight callers) is read as a 1-element list.
        if "sort_by" in data and data["sort_by"]:
            sort_by = [SortBy.from_dict(s) for s in data["sort_by"]]
        elif data.get("sort_by_column"):
            sort_by = [SortBy(
                column_id=data["sort_by_column"],
                direction=data.get("sort_by_order") or "asc",
            )]
        else:
            sort_by = []

        oqo = cls(
            get_rows=data["get_rows"],
            # Back-compat: absent ⇒ "core" (prior default-exclusion behavior).
            corpus=data.get("corpus") or "core",
            filter_rows=filter_rows,
            sort_by=sort_by,
            sample=data.get("sample"),
            group_by=group_by,
            # `select` values are now validated against the registry `column`
            # capability (#450) instead of the old MessageSchema namespace;
            # the vocabularies are string-identical, so pre-#450 dicts parse
            # and validate exactly as before.
            select=list(data.get("select") or []),
            # Coerce an integer `seed` to its string form at the JSON-input
            # boundary (#631). The seed only routes ES `random_score` /
            # `preference` (which hashes it via `.encode()`), so a bare int used
            # to raise AttributeError → HTTP 500 downstream. The OQL text path
            # already canonicalizes `seed 42` to the string "42"; do the same
            # here so both input forms yield an identical canonical OQO. bool is
            # an int subclass but never a valid seed — leave it for the validator.
            seed=(
                str(data["seed"])
                if isinstance(data.get("seed"), int) and not isinstance(data.get("seed"), bool)
                else data.get("seed")
            ),
            per_page=data.get("per_page"),
            page=data.get("page"),
            cursor=data.get("cursor"),
            calculate=[Measure.from_dict(m) for m in data.get("calculate") or []],
            walks=[Walk.from_dict(w) for w in data.get("walks") or []],
            each=bool(data.get("each", False)),
        )
        # Canonicalize alias spellings to one identity at this JSON-input boundary
        # (#455), so a dict carrying `is_oa` / `institution.id` deserializes to the
        # same OQO as its canonical spelling. Idempotent; aliases stay accepted.
        return canonicalize_oqo_column_ids(oqo)


# Valid leaf operators (strictly affirmative — negation is the `is_negated` bit,
# not an operator). The old `is not` / `does not have` were dropped in the
# #284 spec: one negation mechanism only. `has` is the search operator (renamed
# from `contains` in #363 decision 27 — shorter, friendlier, fits a monitor).
VALID_OPERATORS = {
    "is",
    ">", ">=", "<", "<=",
    "has",
    # Membership in a named Collection (col_… set). Distinct from `is` because the
    # intent + value space differ; negation still rides the is_negated bit. The
    # value is always a `col_…` id. See oql-spec §3.10. (oxjob #363)
    "in collection",
}

# Metric-aggregate group sort (oxjob #389): a `SortBy.aggregate` orders group_by
# buckets by a metric sub-aggregation of its (numeric) column. Mirrors
# core.group_by.buckets.GROUP_BY_METRICS keys; kept here (the subsystem's shared
# data-model module) so neither the validator nor the URL parser imports the
# elasticsearch-heavy buckets module — and so they can't drift from each other.
VALID_SORT_AGGREGATES = frozenset({"mean", "sum", "min", "max"})

# Valid corpus selections (#481). "core" is the default; "expansion" is the
# expansion corpus alone (subsumes the retired `is_xpac` filter); "all" is both.
VALID_CORPORA = {"core", "expansion", "all"}

# Surface aliases accepted in the OQL corpus parenthetical, normalized →
# canonical value. Keys are lowercased + single-spaced. "xpac" stays accepted as
# the internal-term alias even though the user-facing word is "expansion".
CORPUS_ALIASES = {
    "core": "core", "core corpus": "core",
    "all": "all", "all corpora": "all",
    "expansion": "expansion", "expansion corpus": "expansion",
    "xpac": "expansion", "xpac corpus": "expansion",
}

# Canonical surface phrase the renderer emits for each non-default corpus.
CORPUS_CANONICAL_PHRASE = {
    "all": "all corpora",
    "expansion": "expansion corpus",
}


def normalize_corpus(text):
    """Map an OQL corpus-parenthetical surface phrase to its canonical value.

    Returns None if the phrase isn't a recognized corpus alias (caller decides
    whether that's an error). Case- and whitespace-insensitive."""
    if text is None:
        return None
    key = " ".join(str(text).strip().lower().split())
    return CORPUS_ALIASES.get(key)


# Valid entity types
VALID_ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "countries",
    "continents", "domains", "fields", "subfields", "sdgs",
    "languages", "licenses", "types", "source-types",
    "institution-types", "awards", "locations", "oa-statuses",
    "indexes", "source-lists", "study-designs"
}
