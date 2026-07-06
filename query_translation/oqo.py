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
    value: Union[str, int, bool, None]
    operator: str = "is"
    is_negated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "column_id": self.column_id,
            "value": self.value,
        }
        if self.operator != "is":
            result["operator"] = self.operator
        if self.is_negated:
            result["is_negated"] = True
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeafFilter":
        return cls(
            column_id=data["column_id"],
            value=data["value"],
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
        filters = []
        for f in data["filters"]:
            if "join" in f:
                filters.append(BranchFilter.from_dict(f))
            else:
                filters.append(LeafFilter.from_dict(f))
        return cls(join=data["join"], filters=filters,
                   is_negated=data.get("is_negated", False))


FilterType = Union[LeafFilter, BranchFilter]


def filter_from_dict(data: Dict[str, Any]) -> FilterType:
    """Convert a dict to either LeafFilter or BranchFilter."""
    if "join" in data:
        return BranchFilter.from_dict(data)
    else:
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
    entity = oqo.get_rows

    def _canon(column_id):
        return canonicalize_column_id(column_id, entity)

    def _canon_filter(f):
        if isinstance(f, BranchFilter):
            return replace(f, filters=[_canon_filter(x) for x in f.filters])
        return replace(f, column_id=_canon(f.column_id))

    return replace(
        oqo,
        filter_rows=[_canon_filter(f) for f in oqo.filter_rows],
        sort_by=[replace(s, column_id=_canon(s.column_id)) for s in oqo.sort_by],
        group_by=[replace(g, column_id=_canon(g.column_id)) for g in oqo.group_by],
    )


@dataclass
class GroupBy:
    """A single group-by dimension.

    `group_by` on the OQO is a *list* of these, so multi-dimensional grouping
    (e.g. topic × year) is expressible in the spec. The live serving impl is
    single-dimension only; multi-dim impl is deferred to a follow-up job (#297).
    """
    column_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"column_id": self.column_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupBy":
        return cls(column_id=data["column_id"])


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

    Beyond *query semantics* (which rows match, sort, group, sample), the OQO
    also carries the "logistics" every OXURL carries so it can fully stand in
    for a `/:entity` request (#318): column projection (`select`), the sample
    `seed`, and pagination (`per_page`/`page`/`cursor`). These five are all
    back-compatible additions — absent ⇒ the prior behavior.
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
    # --- logistics layer (#318) ------------------------------------------
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

        if self.group_by:
            result["group_by"] = [g.to_dict() for g in self.group_by]

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
            seed=data.get("seed"),
            per_page=data.get("per_page"),
            page=data.get("page"),
            cursor=data.get("cursor"),
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
    "institution-types", "awards", "locations", "oa-statuses"
}
