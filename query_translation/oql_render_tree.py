"""
OQL Render Tree - UI-oriented data model for rendering OQL.

This module defines the oql_render tree structure that enables grammar-less
rendering of OQL in the client. The tree can be stringified to produce the
exact normalized OQL string (Invariant A: stringify(oql_render) === oql).

See docs/oql-spec.md and the oql-oqo-plan.md for details.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union, Literal, Any, Dict


# Valid entity types (mirrors OQO)
EntityType = Literal[
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "awards",
    "countries", "continents", "domains", "fields", "subfields",
    "sdgs", "languages", "licenses", "types", "source-types",
    "institution-types", "locations", "oa-statuses"
]

# Valid operators (mirrors OQO)  
Operator = Literal[
    "is", "is not", ">", ">=", "<", "<=", "contains", "does not contain"
]

# Segment kinds for styling
SegmentKind = Literal["keyword", "column", "operator", "value", "id", "text"]

# Clause kinds for UI styling hints
ClauseKind = Literal["boolean", "entity", "comparison", "text", "null", "other"]

# Typed values
TypedValue = Union[str, int, float, bool, None]


@dataclass
class SegmentMeta:
    """Optional metadata for a segment."""
    column_id: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[TypedValue] = None
    entity_id: Optional[str] = None
    entity_short_id: Optional[str] = None
    entity_display_name: Optional[str] = None  # Human-readable name, e.g., "Harvard University"
    entity_display_id: Optional[str] = None    # Bracketed ID for display, e.g., "[i19820366]"

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.column_id is not None:
            result["column_id"] = self.column_id
        if self.operator is not None:
            result["operator"] = self.operator
        if self.value is not None:
            result["value"] = self.value
        if self.entity_id is not None:
            result["entity_id"] = self.entity_id
        if self.entity_short_id is not None:
            result["entity_short_id"] = self.entity_short_id
        if self.entity_display_name is not None:
            result["entity_display_name"] = self.entity_display_name
        if self.entity_display_id is not None:
            result["entity_display_id"] = self.entity_display_id
        return result


@dataclass
class Segment:
    """A renderable segment of text within a clause or directive."""
    kind: SegmentKind
    text: str
    meta: Optional[SegmentMeta] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "kind": self.kind,
            "text": self.text
        }
        if self.meta:
            meta_dict = self.meta.to_dict()
            if meta_dict:
                result["meta"] = meta_dict
        return result


@dataclass
class EntityValue:
    """Resolved entity information for display."""
    id: str
    short_id: str
    display_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "short_id": self.short_id
        }
        if self.display_name is not None:
            result["display_name"] = self.display_name
        return result


@dataclass
class ClauseMeta:
    """Semantic metadata for a clause."""
    column_id: str
    operator: str
    value: TypedValue
    column_display_name: Optional[str] = None
    value_entity: Optional[EntityValue] = None
    source_pointer: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "column_id": self.column_id,
            "operator": self.operator,
            "value": self.value
        }
        if self.column_display_name is not None:
            result["column_display_name"] = self.column_display_name
        if self.value_entity is not None:
            result["value_entity"] = self.value_entity.to_dict()
        else:
            result["value_entity"] = None
        if self.source_pointer is not None:
            result["source_pointer"] = self.source_pointer
        return result


@dataclass
class GroupMeta:
    """Optional metadata for group nodes."""
    implicit: bool = False
    source_pointer: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"implicit": self.implicit}
        if self.source_pointer is not None:
            result["source_pointer"] = self.source_pointer
        return result


@dataclass
class ClauseNode:
    """A leaf clause corresponding to one OQO leaf filter."""
    segments: List[Segment]
    meta: ClauseMeta
    clause_kind: Optional[ClauseKind] = None
    
    @property
    def type(self) -> str:
        return "clause"
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "type": "clause",
            "segments": [s.to_dict() for s in self.segments],
            "meta": self.meta.to_dict()
        }
        if self.clause_kind is not None:
            result["clause_kind"] = self.clause_kind
        return result


@dataclass
class GroupNode:
    """A boolean group combining child expressions."""
    join: Literal["and", "or"]
    children: List[Union["GroupNode", ClauseNode]]
    prefix: str = ""
    suffix: str = ""
    joiner: str = " and "
    meta: Optional[GroupMeta] = None
    
    @property
    def type(self) -> str:
        return "group"
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "type": "group",
            "join": self.join,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "joiner": self.joiner,
            "children": [c.to_dict() for c in self.children]
        }
        if self.meta is not None:
            result["meta"] = self.meta.to_dict()
        return result


# Expression node type
ExprNode = Union[GroupNode, ClauseNode]


@dataclass
class SortMeta:
    """Metadata for sort directive."""
    column_id: str
    order: Literal["asc", "desc"]
    column_display_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "column_id": self.column_id,
            "order": self.order
        }
        if self.column_display_name is not None:
            result["column_display_name"] = self.column_display_name
        return result


@dataclass
class SampleMeta:
    """Metadata for sample directive."""
    n: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {"n": self.n}


@dataclass
class SortDirective:
    """Sorting directive."""
    prefix: str
    segments: List[Segment]
    meta: SortMeta
    
    @property
    def type(self) -> str:
        return "sort"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "sort",
            "prefix": self.prefix,
            "segments": [s.to_dict() for s in self.segments],
            "meta": self.meta.to_dict()
        }


@dataclass
class SampleDirective:
    """Sampling directive."""
    prefix: str
    segments: List[Segment]
    meta: SampleMeta
    
    @property
    def type(self) -> str:
        return "sample"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "sample",
            "prefix": self.prefix,
            "segments": [s.to_dict() for s in self.segments],
            "meta": self.meta.to_dict()
        }


DirectiveNode = Union[SortDirective, SampleDirective]


@dataclass
class EntityHead:
    """The leading entity type portion of the OQL statement."""
    id: str  # e.g., "works"
    text: str  # e.g., "Works"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text
        }


@dataclass
class OQLRenderTree:
    """
    The complete oql_render tree structure.
    
    Stringifying this tree must reproduce the normalized OQL string exactly
    (Invariant A).
    """
    version: str
    entity: EntityHead
    where_keyword: str  # " where " or ""
    where: Optional[ExprNode]  # None if no filters
    directives: List[DirectiveNode] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "entity": self.entity.to_dict(),
            "where_keyword": self.where_keyword,
            "where": self.where.to_dict() if self.where else None,
            "directives": [d.to_dict() for d in self.directives]
        }


def stringify(tree: OQLRenderTree) -> str:
    """
    Convert an OQLRenderTree to its OQL string representation.
    
    This function MUST satisfy Invariant A: stringify(oql_render) === oql
    
    Args:
        tree: The OQL render tree to stringify
    
    Returns:
        The normalized OQL string
    """
    parts = []
    
    # Entity head
    parts.append(tree.entity.text)
    
    # Where keyword (includes spaces if present)
    parts.append(tree.where_keyword)
    
    # Where expression
    if tree.where:
        parts.append(_stringify_expr(tree.where))
    
    # Directives
    for directive in tree.directives:
        parts.append(_stringify_directive(directive))
    
    return "".join(parts)


def _stringify_expr(node: ExprNode) -> str:
    """Stringify an expression node (group or clause)."""
    if isinstance(node, ClauseNode):
        return _stringify_clause(node)
    elif isinstance(node, GroupNode):
        return _stringify_group(node)
    return ""


def _stringify_clause(clause: ClauseNode) -> str:
    """Stringify a clause by concatenating its segments."""
    return "".join(seg.text for seg in clause.segments)


def _stringify_group(group: GroupNode) -> str:
    """Stringify a group with its prefix, children joined by joiner, and suffix."""
    child_strs = [_stringify_expr(child) for child in group.children]
    joined = group.joiner.join(child_strs)
    return f"{group.prefix}{joined}{group.suffix}"


def _stringify_directive(directive: DirectiveNode) -> str:
    """Stringify a directive (sort or sample)."""
    segments_text = "".join(seg.text for seg in directive.segments)
    return f"{directive.prefix}{segments_text}"
