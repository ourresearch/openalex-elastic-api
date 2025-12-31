"""
OQO (OpenAlex Query Object) Data Model

The canonical JSON representation for query format translation.
All translations go through OQO as the intermediate format.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union, Literal, Any, Dict


@dataclass
class LeafFilter:
    """A single filter condition."""
    column_id: str
    value: Union[str, int, bool, None]
    operator: str = "is"
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "column_id": self.column_id,
            "value": self.value,
        }
        if self.operator != "is":
            result["operator"] = self.operator
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeafFilter":
        return cls(
            column_id=data["column_id"],
            value=data["value"],
            operator=data.get("operator", "is")
        )


@dataclass
class BranchFilter:
    """A boolean combination of filters."""
    join: Literal["and", "or"]
    filters: List[Union["LeafFilter", "BranchFilter"]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "join": self.join,
            "filters": [f.to_dict() for f in self.filters]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BranchFilter":
        filters = []
        for f in data["filters"]:
            if "join" in f:
                filters.append(BranchFilter.from_dict(f))
            else:
                filters.append(LeafFilter.from_dict(f))
        return cls(join=data["join"], filters=filters)


FilterType = Union[LeafFilter, BranchFilter]


def filter_from_dict(data: Dict[str, Any]) -> FilterType:
    """Convert a dict to either LeafFilter or BranchFilter."""
    if "join" in data:
        return BranchFilter.from_dict(data)
    else:
        return LeafFilter.from_dict(data)


@dataclass
class OQO:
    """OpenAlex Query Object - the canonical query representation."""
    get_rows: str
    filter_rows: List[FilterType] = field(default_factory=list)
    sort_by_column: Optional[str] = None
    sort_by_order: Optional[Literal["asc", "desc"]] = None
    sample: Optional[int] = None
    
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
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OQO":
        filter_rows = [filter_from_dict(f) for f in data.get("filter_rows", [])]
        
        return cls(
            get_rows=data["get_rows"],
            filter_rows=filter_rows,
            sort_by_column=data.get("sort_by_column"),
            sort_by_order=data.get("sort_by_order"),
            sample=data.get("sample")
        )


# Valid operators
VALID_OPERATORS = {
    "is", "is not", 
    ">", ">=", "<", "<=",
    "contains", "does not contain"
}

# Valid entity types
VALID_ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "countries",
    "continents", "domains", "fields", "subfields", "sdgs",
    "languages", "licenses", "types", "source-types", 
    "institution-types", "awards", "locations", "oa-statuses"
}
