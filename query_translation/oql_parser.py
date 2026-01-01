"""
OQL Parser - Converts OQL (human-readable query language) to OQO format.

Parses both technical and human-readable OQL strings:
  Technical: Works where open_access.is_oa is true and publication_year >= 2020
  Human-readable: Works where it's Open Access and year >= 2020

See docs/oql-spec.md for the full specification.
"""

import re
from typing import Optional, Dict, List, Tuple, Any, Union
from dataclasses import dataclass

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


@dataclass
class ParseError:
    """Represents a parsing error."""
    message: str
    position: Optional[int] = None
    context: Optional[str] = None


class OQLParseError(Exception):
    """Raised when OQL parsing fails."""
    def __init__(self, message: str, errors: Optional[List[ParseError]] = None):
        super().__init__(message)
        self.errors = errors or []


# Reverse mapping: display name -> column_id
DISPLAY_NAME_TO_COLUMN: Dict[str, str] = {
    "year": "publication_year",
    "citations": "cited_by_count",
    "fwci": "fwci",
    "type": "type",
    "open access": "open_access.is_oa",
    "institution": "authorships.institutions.lineage",
    "author": "authorships.author.id",
    "country": "authorships.countries",
    "continent": "authorships.institutions.continent",
    "source": "primary_location.source.id",
    "source type": "primary_location.source.type",
    "publisher": "primary_location.source.publisher_lineage",
    "topic": "primary_topic.id",
    "subfield": "primary_topic.subfield.id",
    "field": "primary_topic.field.id",
    "domain": "primary_topic.domain.id",
    "funder": "grants.funder",
    "sustainable development goals": "sustainable_development_goals.id",
    "sdgs": "sustainable_development_goals.id",
    "title & abstract": "title_and_abstract.search",
    "title": "display_name.search",
    "fulltext": "default.search",
    "raw affiliation string": "raw_affiliation_strings.search",
    "language": "language",
    "retracted": "is_retracted",
    "has a doi": "has_doi",
    "has an abstract": "has_abstract",
    "from global south": "institutions.is_global_south",
    "keyword": "keywords.id",
    "concept": "concepts.id",
    "oa status": "open_access.oa_status",
    "license": "best_oa_location.license",
    "indexed by doaj": "primary_location.source.is_in_doaj",
    "in an oa source": "primary_location.source.is_oa",
    "has repository fulltext": "open_access.any_repository_has_fulltext",
}

# Boolean display names for "it's [not] X" pattern
BOOLEAN_DISPLAY_NAMES: Dict[str, str] = {
    "open access": "open_access.is_oa",
    "retracted": "is_retracted",
    "has a doi": "has_doi",
    "has an abstract": "has_abstract",
    "from global south": "institutions.is_global_south",
    "indexed by doaj": "primary_location.source.is_in_doaj",
    "in an oa source": "primary_location.source.is_oa",
    "has repository fulltext": "open_access.any_repository_has_fulltext",
}

# Valid entity types
VALID_ENTITY_TYPES = {
    "works", "authors", "institutions", "sources", "publishers",
    "funders", "topics", "keywords", "concepts", "countries",
    "continents", "domains", "fields", "subfields", "sdgs",
    "languages", "licenses", "types", "source-types", "source types",
    "institution-types", "institution types", "awards", "locations", "oa-statuses"
}

# Column ID to entity type prefix mapping (for expanding short IDs)
COLUMN_TO_ENTITY_TYPE: Dict[str, str] = {
    "authorships.countries": "countries",
    "authorships.institutions.continent": "continents",
    "authorships.institutions.lineage": "institutions",
    "authorships.author.id": "authors",
    "primary_location.source.id": "sources",
    "primary_location.source.type": "source-types",
    "primary_location.source.publisher_lineage": "publishers",
    "primary_topic.id": "topics",
    "primary_topic.subfield.id": "subfields",
    "primary_topic.field.id": "fields",
    "primary_topic.domain.id": "domains",
    "grants.funder": "funders",
    "awards.funder.id": "funders",
    "sustainable_development_goals.id": "sdgs",
    "language": "languages",
    "type": "types",
    "keywords.id": "keywords",
    "concepts.id": "concepts",
    "open_access.oa_status": "oa-statuses",
    "best_oa_location.license": "licenses",
}

# Operators in order of precedence (longest first for matching)
OPERATORS = [
    "is not",
    "does not contain",
    "is greater than or equal to",
    "is less than or equal to",
    "is greater than",
    "is less than",
    ">=",
    "<=",
    ">",
    "<",
    "is",
    "contains",
]


class OQLParser:
    """
    Parses OQL strings into OQO objects.
    
    Supports both technical and human-readable formats.
    """
    
    def __init__(self):
        self._errors: List[ParseError] = []
    
    def parse(self, oql: str) -> OQO:
        """
        Parse an OQL string into an OQO object.
        
        Args:
            oql: The OQL string to parse
        
        Returns:
            OQO object
        
        Raises:
            OQLParseError: If parsing fails
        """
        self._errors = []
        oql = oql.strip()
        
        if not oql:
            raise OQLParseError("Empty OQL string")
        
        # Parse entity type
        entity_type, remainder = self._parse_entity_type(oql)
        
        # Initialize result
        filter_rows: List[FilterType] = []
        sort_by_column: Optional[str] = None
        sort_by_order: Optional[str] = None
        sample: Optional[int] = None
        
        # Check for "where" clause
        if remainder:
            remainder = remainder.strip()
            
            # Split by semicolons to separate filters from sort/sample
            parts = self._split_by_semicolon(remainder)
            
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                
                if i == 0 and part.lower().startswith("where "):
                    # First part is the filter clause
                    filter_str = part[6:].strip()  # Remove "where "
                    filter_rows = self._parse_filters(filter_str)
                elif part.lower().startswith("sort by "):
                    sort_str = part[8:].strip()  # Remove "sort by "
                    sort_by_column, sort_by_order = self._parse_sort(sort_str)
                elif part.lower().startswith("sample "):
                    sample_str = part[7:].strip()  # Remove "sample "
                    try:
                        sample = int(sample_str)
                    except ValueError:
                        self._add_error(f"Invalid sample value: {sample_str}")
        
        if self._errors:
            raise OQLParseError("Failed to parse OQL", self._errors)
        
        return OQO(
            get_rows=entity_type,
            filter_rows=filter_rows,
            sort_by_column=sort_by_column,
            sort_by_order=sort_by_order,
            sample=sample
        )
    
    def _parse_entity_type(self, oql: str) -> Tuple[str, str]:
        """Parse the entity type from the start of the OQL string."""
        oql_lower = oql.lower()
        
        # Try to match entity types (sorted by length, longest first)
        sorted_types = sorted(VALID_ENTITY_TYPES, key=len, reverse=True)
        
        for entity_type in sorted_types:
            if oql_lower.startswith(entity_type + " ") or oql_lower == entity_type:
                remainder = oql[len(entity_type):].strip()
                # Normalize entity type
                normalized = entity_type.replace(" ", "-").lower()
                return normalized, remainder
        
        # Try to extract first word as entity type
        match = re.match(r'^(\w+(?:\s+\w+)?)\s*', oql, re.IGNORECASE)
        if match:
            possible_type = match.group(1).lower().replace(" ", "-")
            if possible_type in VALID_ENTITY_TYPES or possible_type.replace("-", " ") in VALID_ENTITY_TYPES:
                remainder = oql[match.end():].strip()
                return possible_type, remainder
        
        self._add_error(f"Could not parse entity type from: {oql[:50]}")
        # Default to works
        return "works", oql
    
    def _split_by_semicolon(self, text: str) -> List[str]:
        """Split text by semicolons, respecting quoted strings."""
        parts = []
        current = ""
        in_quotes = False
        
        for char in text:
            # Only double quotes are string delimiters
            if char == '"' and not in_quotes:
                in_quotes = True
                current += char
            elif char == '"' and in_quotes:
                in_quotes = False
                current += char
            elif char == ";" and not in_quotes:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def _parse_filters(self, filter_str: str) -> List[FilterType]:
        """Parse the filter clause into a list of filters."""
        filters = []
        
        # Split by " and " at top level, respecting parentheses
        clauses = self._split_by_and(filter_str)
        
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
            
            parsed = self._parse_single_clause(clause)
            if parsed:
                filters.append(parsed)
        
        return filters
    
    def _split_by_and(self, text: str) -> List[str]:
        """Split text by ' and ' at top level, respecting parentheses and quotes."""
        parts = []
        current = ""
        depth = 0
        in_quotes = False
        i = 0
        
        while i < len(text):
            char = text[i]
            
            # Handle double quotes only (single quotes/apostrophes in "it's" should not be string delimiters)
            if char == '"' and not in_quotes:
                in_quotes = True
                current += char
            elif char == '"' and in_quotes:
                in_quotes = False
                current += char
            elif char == "(" and not in_quotes:
                depth += 1
                current += char
            elif char == ")" and not in_quotes:
                depth -= 1
                current += char
            elif depth == 0 and not in_quotes:
                # Check for " and " (case insensitive)
                if text[i:i+5].lower() == " and ":
                    parts.append(current.strip())
                    current = ""
                    i += 4  # Skip " and" (will increment by 1 more below)
                else:
                    current += char
            else:
                current += char
            
            i += 1
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def _parse_single_clause(self, clause: str) -> Optional[FilterType]:
        """Parse a single filter clause."""
        clause = clause.strip()
        
        if not clause:
            return None
        
        # Check for parenthesized OR expression
        if clause.startswith("(") and clause.endswith(")"):
            inner = clause[1:-1].strip()
            return self._parse_or_expression(inner)
        
        # Check for "it's [not] X" boolean pattern
        boolean_filter = self._parse_boolean_pattern(clause)
        if boolean_filter:
            return boolean_filter
        
        # Parse regular filter: column operator value
        return self._parse_standard_filter(clause)
    
    def _parse_or_expression(self, inner: str) -> Optional[FilterType]:
        """Parse an OR expression inside parentheses."""
        # Split by " or " at this level
        parts = self._split_by_or(inner)
        
        if len(parts) == 1:
            # No OR found, parse as regular clause
            return self._parse_single_clause(parts[0])
        
        filters = []
        for part in parts:
            parsed = self._parse_single_clause(part.strip())
            if parsed:
                filters.append(parsed)
        
        if not filters:
            return None
        
        if len(filters) == 1:
            return filters[0]
        
        return BranchFilter(join="or", filters=filters)
    
    def _split_by_or(self, text: str) -> List[str]:
        """Split text by ' or ' at current level."""
        parts = []
        current = ""
        depth = 0
        in_quotes = False
        i = 0
        
        while i < len(text):
            char = text[i]
            
            # Only double quotes are string delimiters
            if char == '"' and not in_quotes:
                in_quotes = True
                current += char
            elif char == '"' and in_quotes:
                in_quotes = False
                current += char
            elif char == "(" and not in_quotes:
                depth += 1
                current += char
            elif char == ")" and not in_quotes:
                depth -= 1
                current += char
            elif depth == 0 and not in_quotes:
                if text[i:i+4].lower() == " or ":
                    parts.append(current.strip())
                    current = ""
                    i += 3
                else:
                    current += char
            else:
                current += char
            
            i += 1
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def _parse_boolean_pattern(self, clause: str) -> Optional[LeafFilter]:
        """
        Parse "it's [not] X" boolean pattern.
        
        Examples:
        - "it's Open Access" -> open_access.is_oa = true
        - "it's not retracted" -> is_retracted = false
        """
        clause_lower = clause.lower()
        
        # Check for "it's not X" pattern
        match = re.match(r"it'?s\s+not\s+(.+)", clause, re.IGNORECASE)
        if match:
            display_name = match.group(1).strip().lower()
            column_id = BOOLEAN_DISPLAY_NAMES.get(display_name)
            if column_id:
                return LeafFilter(column_id=column_id, value=False, operator="is")
        
        # Check for "it's X" pattern
        match = re.match(r"it'?s\s+(.+)", clause, re.IGNORECASE)
        if match:
            display_name = match.group(1).strip().lower()
            column_id = BOOLEAN_DISPLAY_NAMES.get(display_name)
            if column_id:
                return LeafFilter(column_id=column_id, value=True, operator="is")
        
        # Check for "it has/doesn't have" pattern
        match = re.match(r"it\s+has\s+(.+)", clause, re.IGNORECASE)
        if match:
            display_name = "has " + match.group(1).strip().lower()
            column_id = BOOLEAN_DISPLAY_NAMES.get(display_name)
            if column_id:
                return LeafFilter(column_id=column_id, value=True, operator="is")
        
        match = re.match(r"it\s+doesn'?t\s+have\s+(.+)", clause, re.IGNORECASE)
        if match:
            display_name = "has " + match.group(1).strip().lower()
            column_id = BOOLEAN_DISPLAY_NAMES.get(display_name)
            if column_id:
                return LeafFilter(column_id=column_id, value=False, operator="is")
        
        return None
    
    def _parse_standard_filter(self, clause: str) -> Optional[LeafFilter]:
        """
        Parse a standard filter: column operator value
        
        Examples:
        - "year >= 2020"
        - "Country is Canada [countries/ca]"
        - "type is [types/article]"
        """
        # Try each operator
        for op in OPERATORS:
            # Find operator in clause (case insensitive for text operators)
            if op in (">=", "<=", ">", "<"):
                idx = clause.find(op)
            else:
                # Case insensitive search
                idx = clause.lower().find(op.lower())
            
            if idx != -1:
                column_part = clause[:idx].strip()
                value_part = clause[idx + len(op):].strip()
                
                # Resolve column name
                column_id = self._resolve_column(column_part)
                
                # Parse value (pass column_id for short ID expansion)
                value, extracted_op = self._parse_value(value_part, op, column_id)
                
                # Map operator
                operator = self._normalize_operator(extracted_op or op)
                
                return LeafFilter(column_id=column_id, value=value, operator=operator)
        
        self._add_error(f"Could not parse filter clause: {clause}")
        return None
    
    def _resolve_column(self, column_str: str) -> str:
        """Resolve a column name (display name or column_id) to column_id."""
        column_str = column_str.strip()
        column_lower = column_str.lower()
        
        # Check if it's already a valid column_id (contains dots or underscores)
        if "." in column_str or "_" in column_str:
            return column_str
        
        # Look up in display name mapping
        if column_lower in DISPLAY_NAME_TO_COLUMN:
            return DISPLAY_NAME_TO_COLUMN[column_lower]
        
        # Return as-is (might be a valid column_id)
        return column_str
    
    def _parse_value(self, value_str: str, operator: str, column_id: Optional[str] = None) -> Tuple[Any, Optional[str]]:
        """
        Parse a filter value.
        
        Handles:
        - Bracketed IDs: [countries/ca], Canada [countries/ca], [ca], Canada [ca]
        - Quoted strings: "machine learning"
        - Numbers: 2020, 100.5
        - Booleans: true, false
        - Null: null, unknown
        
        For short IDs (without entity type prefix), the entity type is inferred
        from the column_id being filtered.
        
        Returns:
            Tuple of (parsed_value, modified_operator)
        """
        value_str = value_str.strip()
        
        # Check for "unknown" or "null"
        if value_str.lower() in ("null", "unknown"):
            return None, None
        
        # Check for bracketed ID with optional display name before it
        # Pattern: "Display Name [entity_type/id]" or "[entity_type/id]" or "[short_id]"
        bracket_match = re.search(r'\[([^\]]+)\]', value_str)
        if bracket_match:
            entity_id = bracket_match.group(1)
            # If ID doesn't contain a slash, it's a short ID - expand it
            if "/" not in entity_id and column_id:
                entity_type = COLUMN_TO_ENTITY_TYPE.get(column_id)
                if entity_type:
                    entity_id = f"{entity_type}/{entity_id}"
            return entity_id, None
        
        # Check for quoted string
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1], None
        
        # Check for boolean
        if value_str.lower() == "true":
            return True, None
        if value_str.lower() == "false":
            return False, None
        
        # Check for number
        try:
            if "." in value_str:
                return float(value_str), None
            return int(value_str), None
        except ValueError:
            pass
        
        # Return as string
        return value_str, None
    
    def _normalize_operator(self, op: str) -> str:
        """Normalize operator to standard form."""
        op_lower = op.lower().strip()
        
        mappings = {
            "is greater than or equal to": ">=",
            "is less than or equal to": "<=",
            "is greater than": ">",
            "is less than": "<",
        }
        
        return mappings.get(op_lower, op_lower)
    
    def _parse_sort(self, sort_str: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse sort clause."""
        parts = sort_str.split()
        
        if not parts:
            return None, None
        
        column = parts[0]
        order = parts[1] if len(parts) > 1 else "desc"
        
        # Resolve column name
        column_id = self._resolve_column(column)
        
        # Also check sort-specific mappings
        sort_mappings = {
            "citations": "cited_by_count",
            "year": "publication_year",
            "date": "publication_date",
            "relevance": "relevance_score",
        }
        if column.lower() in sort_mappings:
            column_id = sort_mappings[column.lower()]
        
        return column_id, order.lower()
    
    def _add_error(self, message: str, position: Optional[int] = None):
        """Add a parsing error."""
        self._errors.append(ParseError(message=message, position=position))


def parse_oql_to_oqo(oql: str) -> OQO:
    """
    Parse an OQL string into an OQO object.
    
    Args:
        oql: The OQL string to parse
    
    Returns:
        OQO object
    
    Raises:
        OQLParseError: If parsing fails
    """
    parser = OQLParser()
    return parser.parse(oql)
