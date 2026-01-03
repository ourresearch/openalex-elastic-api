"""
OQL Tree Renderer - Converts OQO to both OQL string and oql_render tree.

This renderer produces both:
1. oql: The normalized OQL string
2. oql_render: A structured tree for UI rendering

The key invariant is: stringify(oql_render) === oql

See oql-oqo-plan.md for specification.
"""

from typing import Optional, Dict, Any, Callable, Tuple, List

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType
from query_translation.oql_render_tree import (
    OQLRenderTree, EntityHead, GroupNode, ClauseNode, Segment, SegmentMeta,
    ClauseMeta, GroupMeta, EntityValue, SortDirective, SampleDirective,
    SortMeta, SampleMeta, ExprNode, stringify
)


# Column ID to display name mapping
COLUMN_DISPLAY_NAMES: Dict[str, str] = {
    "publication_year": "year",
    "cited_by_count": "citations",
    "fwci": "FWCI",
    "type": "type",
    "open_access.is_oa": "Open Access",
    "authorships.institutions.lineage": "institution",
    "authorships.author.id": "author",
    "authorships.countries": "Country",
    "authorships.institutions.continent": "Continent",
    "primary_location.source.id": "source",
    "primary_location.source.type": "source type",
    "primary_location.source.publisher_lineage": "publisher",
    "primary_topic.id": "topic",
    "primary_topic.subfield.id": "subfield",
    "primary_topic.field.id": "field",
    "primary_topic.domain.id": "domain",
    "grants.funder": "funder",
    "awards.funder.id": "funder",
    "sustainable_development_goals.id": "Sustainable Development Goals",
    "title_and_abstract.search": "title & abstract",
    "display_name.search": "title",
    "default.search": "fulltext",
    "raw_affiliation_strings.search": "raw affiliation string",
    "language": "language",
    "is_retracted": "retracted",
    "has_doi": "has a DOI",
    "has_abstract": "has an abstract",
    "institutions.is_global_south": "from Global South",
    "authorships.institutions.is_global_south": "from Global South",
    "keywords.id": "keyword",
    "concepts.id": "concept",
    "open_access.oa_status": "OA status",
    "best_oa_location.license": "license",
}

# Boolean columns that use "it's [not] {displayName}" format
BOOLEAN_COLUMNS: Dict[str, str] = {
    "open_access.is_oa": "Open Access",
    "is_retracted": "retracted",
    "has_doi": "has a DOI",
    "has_abstract": "has an abstract",
    "institutions.is_global_south": "from Global South",
    "authorships.institutions.is_global_south": "from Global South",
    "primary_location.source.is_in_doaj": "indexed by DOAJ",
    "primary_location.source.is_oa": "in an OA source",
    "open_access.any_repository_has_fulltext": "has repository fulltext",
}

# Column ID to entity type mapping (for constructing full entity IDs)
COLUMN_ENTITY_TYPES: Dict[str, str] = {
    "authorships.institutions.lineage": "institutions",
    "authorships.author.id": "authors",
    "authorships.countries": "countries",
    "authorships.institutions.continent": "continents",
    "primary_location.source.id": "sources",
    "primary_location.source.publisher_lineage": "publishers",
    "primary_topic.id": "topics",
    "primary_topic.subfield.id": "subfields",
    "primary_topic.field.id": "fields",
    "primary_topic.domain.id": "domains",
    "grants.funder": "funders",
    "awards.funder.id": "funders",
    "sustainable_development_goals.id": "sdgs",
    "language": "languages",
    "keywords.id": "keywords",
    "concepts.id": "concepts",
    "type": "types",
    "open_access.oa_status": "oa-statuses",
    "best_oa_location.license": "licenses",
}

# Sort column display names
SORT_DISPLAY_NAMES: Dict[str, str] = {
    "cited_by_count": "citations",
    "publication_year": "year",
    "publication_date": "date",
    "fwci": "FWCI",
    "display_name": "title",
    "relevance_score": "relevance",
}


class OQLTreeRenderer:
    """
    Renders OQO objects to both OQL strings and oql_render trees.
    """
    
    VERSION = "1.0"
    
    def __init__(self, entity_resolver: Optional[Callable[[str], Optional[str]]] = None):
        """
        Initialize the renderer.
        
        Args:
            entity_resolver: Optional function that takes an entity ID and returns its display name.
        """
        self._entity_resolver = entity_resolver
        self._entity_cache: Dict[str, str] = {}
    
    def render(self, oqo: OQO) -> Tuple[str, OQLRenderTree]:
        """
        Render an OQO object to both OQL format and render tree.
        
        Args:
            oqo: The OQO object to render
        
        Returns:
            Tuple of (oql_string, oql_render_tree)
        """
        # Build entity head
        entity_name = oqo.get_rows.replace("-", " ").title()
        entity = EntityHead(id=oqo.get_rows, text=entity_name)
        
        # Build where expression
        where_node: Optional[ExprNode] = None
        where_keyword = ""
        
        if oqo.filter_rows:
            where_keyword = " where "
            
            if len(oqo.filter_rows) == 1:
                # Single filter - render directly
                where_node = self._render_filter(oqo.filter_rows[0], "/filter_rows/0")
            else:
                # Multiple filters - create implicit AND group
                children = []
                for i, f in enumerate(oqo.filter_rows):
                    child_node = self._render_filter(f, f"/filter_rows/{i}")
                    if child_node:
                        children.append(child_node)
                
                if children:
                    where_node = GroupNode(
                        join="and",
                        children=children,
                        prefix="",
                        suffix="",
                        joiner=" and ",
                        meta=GroupMeta(implicit=True, source_pointer=None)
                    )
        
        # Build directives
        directives = []
        
        if oqo.sort_by_column:
            sort_directive = self._build_sort_directive(oqo.sort_by_column, oqo.sort_by_order or "desc")
            directives.append(sort_directive)
        
        if oqo.sample:
            sample_directive = self._build_sample_directive(oqo.sample)
            directives.append(sample_directive)
        
        # Build the tree
        tree = OQLRenderTree(
            version=self.VERSION,
            entity=entity,
            where_keyword=where_keyword,
            where=where_node,
            directives=directives
        )
        
        # Stringify to get OQL
        oql = stringify(tree)
        
        return oql, tree
    
    def _render_filter(self, f: FilterType, source_pointer: str) -> Optional[ExprNode]:
        """Render a single filter to an expression node."""
        if isinstance(f, LeafFilter):
            return self._render_leaf_filter(f, source_pointer)
        elif isinstance(f, BranchFilter):
            return self._render_branch_filter(f, source_pointer)
        return None
    
    def _render_leaf_filter(self, f: LeafFilter, source_pointer: str) -> ClauseNode:
        """Render a leaf filter to a clause node."""
        column_id = f.column_id
        value = f.value
        operator = f.operator or "is"
        
        # Determine clause kind
        clause_kind = self._determine_clause_kind(column_id, value, operator)
        
        # Check for boolean filter with special "it's" format
        if column_id in BOOLEAN_COLUMNS:
            bool_value = self._normalize_boolean(value)
            if bool_value is not None:
                return self._render_boolean_clause(column_id, bool_value, operator, source_pointer, clause_kind)
        
        # Get display name for column
        column_display = COLUMN_DISPLAY_NAMES.get(column_id, column_id)
        
        # Build segments based on operator type
        segments = []
        value_entity: Optional[EntityValue] = None
        
        if operator in ("is", "is not"):
            # Entity or simple value clause
            segments.append(Segment(
                kind="column",
                text=column_display,
                meta=SegmentMeta(column_id=column_id)
            ))
            
            operator_text = f" {operator} "
            segments.append(Segment(kind="operator", text=operator_text))
            
            # Format the value
            if value is None:
                segments.append(Segment(
                    kind="value",
                    text="unknown",
                    meta=SegmentMeta(value=None)
                ))
            elif isinstance(value, str) and "/" in value:
                # Entity value with full ID (e.g., "institutions/i33213144")
                value_entity = self._format_entity_segments(value, segments)
            elif isinstance(value, str) and column_id in COLUMN_ENTITY_TYPES:
                # Entity value with short ID - construct full ID from column type
                entity_type = COLUMN_ENTITY_TYPES[column_id]
                full_entity_id = f"{entity_type}/{value}"
                value_entity = self._format_entity_segments(full_entity_id, segments)
            else:
                value_str = self._format_simple_value(value)
                segments.append(Segment(
                    kind="value",
                    text=value_str,
                    meta=SegmentMeta(value=value)
                ))
        
        elif operator in (">", ">=", "<", "<="):
            # Comparison clause
            segments.append(Segment(
                kind="column",
                text=column_display,
                meta=SegmentMeta(column_id=column_id)
            ))
            
            segments.append(Segment(kind="operator", text=f" {operator} "))
            
            value_str = str(value) if value is not None else "unknown"
            segments.append(Segment(
                kind="value",
                text=value_str,
                meta=SegmentMeta(value=value)
            ))
        
        elif operator in ("contains", "does not contain"):
            # Text search clause
            segments.append(Segment(
                kind="column",
                text=column_display,
                meta=SegmentMeta(column_id=column_id)
            ))
            
            segments.append(Segment(kind="operator", text=f" {operator} "))
            
            # Quote string values
            value_str = self._format_text_value(value)
            segments.append(Segment(
                kind="value",
                text=value_str,
                meta=SegmentMeta(value=value)
            ))
        
        else:
            # Fallback for unknown operators
            segments.append(Segment(
                kind="column",
                text=column_display,
                meta=SegmentMeta(column_id=column_id)
            ))
            segments.append(Segment(kind="operator", text=f" {operator} "))
            segments.append(Segment(
                kind="value",
                text=str(value),
                meta=SegmentMeta(value=value)
            ))
        
        return ClauseNode(
            segments=segments,
            meta=ClauseMeta(
                column_id=column_id,
                column_display_name=column_display,
                operator=operator,
                value=value,
                value_entity=value_entity,
                source_pointer=source_pointer
            ),
            clause_kind=clause_kind
        )
    
    def _determine_clause_kind(self, column_id: str, value: Any, operator: str) -> str:
        """Determine the clause kind for UI styling."""
        if column_id in BOOLEAN_COLUMNS:
            return "boolean"
        if value is None:
            return "null"
        if operator in ("contains", "does not contain"):
            return "text"
        if operator in (">", ">=", "<", "<="):
            return "comparison"
        if isinstance(value, str) and "/" in value:
            return "entity"
        if column_id in COLUMN_ENTITY_TYPES:
            return "entity"
        return "other"
    
    def _normalize_boolean(self, value: Any) -> Optional[bool]:
        """Normalize a value to a boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() == "true":
                return True
            if value.lower() == "false":
                return False
        return None
    
    def _render_boolean_clause(
        self, column_id: str, value: bool, operator: str, 
        source_pointer: str, clause_kind: str
    ) -> ClauseNode:
        """Render a boolean filter using "it's [not] {displayName}" format."""
        display_name = BOOLEAN_COLUMNS.get(column_id, column_id)
        
        # Determine if negated
        is_negated = (value is False) or (operator == "is not" and value is True)
        
        if is_negated:
            text = f"it's not {display_name}"
        else:
            text = f"it's {display_name}"
        
        return ClauseNode(
            segments=[
                Segment(kind="keyword", text=text)
            ],
            meta=ClauseMeta(
                column_id=column_id,
                column_display_name=display_name,
                operator="is" if not is_negated else "is not",
                value=True,  # Canonical form
                value_entity=None,
                source_pointer=source_pointer
            ),
            clause_kind=clause_kind
        )
    
    def _format_entity_segments(self, entity_id: str, segments: List[Segment]) -> Optional[EntityValue]:
        """
        Format an entity ID by adding segments for display name and bracketed ID.

        Always creates a "value" segment with clean text (display_name or short_id).
        The bracketed ID segment is only added when there's a display_name, since
        otherwise the ID is already shown in the value segment.

        Metadata always includes:
        - entity_id: full ID like "institutions/i19820366"
        - entity_short_id: short ID like "i19820366"
        - entity_display_name: human name like "Harvard University" (may be None)
        - entity_display_id: bracketed ID like "[i19820366]"

        Returns the EntityValue for metadata.
        """
        display_name = self._resolve_entity_display_name(entity_id)
        short_id = entity_id.split("/", 1)[1] if "/" in entity_id else entity_id
        display_id = f"[{short_id}]"

        # Always create a value segment - use display_name if available, else short_id
        value_text = display_name if display_name else short_id
        segments.append(Segment(
            kind="value",
            text=value_text,
            meta=SegmentMeta(
                entity_id=entity_id,
                entity_short_id=short_id,
                entity_display_name=display_name,  # May be None
                entity_display_id=display_id       # Always "[short_id]"
            )
        ))

        # Only add bracketed ID when we have a display_name (otherwise redundant)
        if display_name:
            segments.append(Segment(kind="text", text=" "))
            segments.append(Segment(
                kind="id",
                text=display_id,
                meta=SegmentMeta(
                    entity_id=entity_id,
                    entity_short_id=short_id,
                    entity_display_id=display_id
                )
            ))

        return EntityValue(
            id=entity_id,
            short_id=short_id,
            display_name=display_name
        )
    
    def _format_simple_value(self, value: Any) -> str:
        """Format a simple (non-entity) value."""
        if value is None:
            return "unknown"
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)
    
    def _format_text_value(self, value: Any) -> str:
        """Format a text value, quoting if necessary."""
        if value is None:
            return "unknown"
        value_str = str(value)
        # Always quote text search values
        if '"' in value_str:
            # Escape internal quotes
            value_str = value_str.replace('"', '\\"')
        return f'"{value_str}"'
    
    def _resolve_entity_display_name(self, entity_id: str) -> Optional[str]:
        """Resolve an entity ID to its display name."""
        if entity_id in self._entity_cache:
            return self._entity_cache[entity_id]
        
        if self._entity_resolver:
            display_name = self._entity_resolver(entity_id)
            if display_name:
                self._entity_cache[entity_id] = display_name
                return display_name
        
        display_name = self._default_entity_resolver(entity_id)
        if display_name:
            self._entity_cache[entity_id] = display_name
        
        return display_name
    
    def _default_entity_resolver(self, entity_id: str) -> Optional[str]:
        """Default entity resolver for well-known entity types."""
        if "/" not in entity_id:
            return None
        
        entity_type, short_id = entity_id.split("/", 1)
        
        if entity_type == "types":
            return short_id.replace("-", " ").title()
        
        if entity_type == "oa-statuses":
            return short_id.title()
        
        if entity_type == "languages":
            return LANGUAGES.get(short_id.lower())
        
        if entity_type == "countries":
            return COUNTRIES.get(short_id.lower())
        
        if entity_type == "continents":
            return CONTINENTS.get(short_id.lower())
        
        if entity_type == "sdgs":
            return SDGS.get(short_id)
        
        return None
    
    def _render_branch_filter(self, f: BranchFilter, source_pointer: str) -> Optional[ExprNode]:
        """Render a branch filter to a group node."""
        if not f.filters:
            return None
        
        children = []
        for i, sub_f in enumerate(f.filters):
            child_node = self._render_filter(sub_f, f"{source_pointer}/filters/{i}")
            if child_node:
                children.append(child_node)
        
        if not children:
            return None
        
        if len(children) == 1:
            return children[0]
        
        # Determine prefix/suffix based on join type
        # OR groups are always parenthesized
        # AND groups inside OR groups should also be parenthesized
        # Top-level AND uses no parens
        if f.join == "or":
            prefix = "("
            suffix = ")"
            joiner = " or "
        else:
            prefix = "("
            suffix = ")"
            joiner = " and "
        
        return GroupNode(
            join=f.join,
            children=children,
            prefix=prefix,
            suffix=suffix,
            joiner=joiner,
            meta=GroupMeta(implicit=False, source_pointer=source_pointer)
        )
    
    def _build_sort_directive(self, column_id: str, order: str) -> SortDirective:
        """Build a sort directive."""
        sort_display = SORT_DISPLAY_NAMES.get(column_id, column_id)
        
        return SortDirective(
            prefix="; sort by ",
            segments=[
                Segment(
                    kind="column",
                    text=sort_display,
                    meta=SegmentMeta(column_id=column_id)
                ),
                Segment(kind="text", text=" "),
                Segment(
                    kind="keyword",
                    text=order
                )
            ],
            meta=SortMeta(
                column_id=column_id,
                column_display_name=sort_display,
                order=order
            )
        )
    
    def _build_sample_directive(self, n: int) -> SampleDirective:
        """Build a sample directive."""
        return SampleDirective(
            prefix="; sample ",
            segments=[
                Segment(
                    kind="value",
                    text=str(n),
                    meta=SegmentMeta(value=n)
                )
            ],
            meta=SampleMeta(n=n)
        )


# Lookup tables for entity resolution
LANGUAGES = {
    "en": "English", "zh": "Chinese", "es": "Spanish", "fr": "French",
    "de": "German", "ja": "Japanese", "pt": "Portuguese", "ru": "Russian",
    "ko": "Korean", "it": "Italian", "ar": "Arabic", "nl": "Dutch",
    "pl": "Polish", "tr": "Turkish", "id": "Indonesian", "cs": "Czech",
    "sv": "Swedish", "fa": "Persian", "uk": "Ukrainian", "vi": "Vietnamese",
}

COUNTRIES = {
    "us": "United States", "gb": "United Kingdom", "cn": "China",
    "de": "Germany", "fr": "France", "jp": "Japan", "ca": "Canada",
    "au": "Australia", "in": "India", "br": "Brazil", "it": "Italy",
    "es": "Spain", "kr": "South Korea", "nl": "Netherlands", "ru": "Russia",
    "ch": "Switzerland", "se": "Sweden", "pl": "Poland", "be": "Belgium",
    "at": "Austria", "dk": "Denmark", "no": "Norway", "fi": "Finland",
    "mx": "Mexico", "sg": "Singapore", "ie": "Ireland", "nz": "New Zealand",
    "pt": "Portugal", "za": "South Africa", "il": "Israel",
}

CONTINENTS = {
    "q15": "Africa", "q18": "South America", "q46": "Europe",
    "q48": "Asia", "q49": "North America", "q55643": "Oceania",
    "q51": "Antarctica", "africa": "Africa", "south america": "South America",
    "europe": "Europe", "asia": "Asia", "north america": "North America",
    "oceania": "Oceania", "antarctica": "Antarctica",
}

SDGS = {
    "1": "No Poverty", "2": "Zero Hunger", "3": "Good Health and Well-being",
    "4": "Quality Education", "5": "Gender Equality",
    "6": "Clean Water and Sanitation", "7": "Affordable and Clean Energy",
    "8": "Decent Work and Economic Growth", "9": "Industry, Innovation and Infrastructure",
    "10": "Reduced Inequalities", "11": "Sustainable Cities and Communities",
    "12": "Responsible Consumption and Production", "13": "Climate Action",
    "14": "Life Below Water", "15": "Life on Land",
    "16": "Peace, Justice, and Strong Institutions", "17": "Partnerships for the Goals",
}


def render_oqo_to_oql_and_tree(
    oqo: OQO, 
    entity_resolver: Optional[Callable[[str], Optional[str]]] = None
) -> Tuple[str, OQLRenderTree]:
    """
    Render an OQO object to both OQL format and render tree.
    
    Args:
        oqo: The OQO object to render
        entity_resolver: Optional function to resolve entity IDs to display names
    
    Returns:
        Tuple of (oql_string, oql_render_tree)
    """
    renderer = OQLTreeRenderer(entity_resolver=entity_resolver)
    return renderer.render(oqo)
