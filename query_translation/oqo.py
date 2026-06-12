"""
OQO (OpenAlex Query Object) Data Model

The canonical JSON representation for query format translation.
All translations go through OQO as the intermediate format.
"""

from dataclasses import dataclass, field, asdict
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
    negation mechanism. (The old `is not` / `does not contain` operators are
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

        return cls(
            get_rows=data["get_rows"],
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


# Valid leaf operators (strictly affirmative — negation is the `is_negated` bit,
# not an operator). The old `is not` / `does not contain` were dropped in the
# #284 spec: one negation mechanism only.
VALID_OPERATORS = {
    "is",
    ">", ">=", "<", "<=",
    "contains",
    # Membership in a named Collection (col_… set). Distinct from `is` because the
    # intent + value space differ; negation still rides the is_negated bit. The
    # value is always a `col_…` id. See oql-spec §3.10. (oxjob #363)
    "in collection",
}

# Valid entity types
VALID_ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "countries",
    "continents", "domains", "fields", "subfields", "sdgs",
    "languages", "licenses", "types", "source-types", 
    "institution-types", "awards", "locations", "oa-statuses"
}
