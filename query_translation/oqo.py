"""
OQO (OpenAlex Query Object) Data Model

The canonical JSON representation for query format translation.
All translations go through OQO as the intermediate format.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union, Literal, Any, Dict


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
class OQO:
    """OpenAlex Query Object - the canonical query representation."""
    get_rows: str
    filter_rows: List[FilterType] = field(default_factory=list)
    sort_by_column: Optional[str] = None
    sort_by_order: Optional[Literal["asc", "desc"]] = None
    sample: Optional[int] = None
    group_by: List[GroupBy] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {"get_rows": self.get_rows}

        if self.filter_rows:
            result["filter_rows"] = [f.to_dict() for f in self.filter_rows]

        if self.sort_by_column:
            result["sort_by_column"] = self.sort_by_column

        if self.sort_by_order:
            result["sort_by_order"] = self.sort_by_order

        if self.sample:
            result["sample"] = self.sample

        if self.group_by:
            result["group_by"] = [g.to_dict() for g in self.group_by]

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OQO":
        filter_rows = [filter_from_dict(f) for f in data.get("filter_rows", [])]
        group_by = [GroupBy.from_dict(g) for g in data.get("group_by", [])]

        return cls(
            get_rows=data["get_rows"],
            filter_rows=filter_rows,
            sort_by_column=data.get("sort_by_column"),
            sort_by_order=data.get("sort_by_order"),
            sample=data.get("sample"),
            group_by=group_by,
        )


# Valid leaf operators (strictly affirmative — negation is the `is_negated` bit,
# not an operator). The old `is not` / `does not contain` were dropped in the
# #284 spec: one negation mechanism only.
VALID_OPERATORS = {
    "is",
    ">", ">=", "<", "<=",
    "contains",
}

# Valid entity types
VALID_ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "countries",
    "continents", "domains", "fields", "subfields", "sdgs",
    "languages", "licenses", "types", "source-types", 
    "institution-types", "awards", "locations", "oa-statuses"
}
