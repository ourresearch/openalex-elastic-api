"""
URL Parser - Converts URL filter strings to OQO format.

Handles the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


def parse_url_to_oqo(
    entity_type: str,
    filter_string: Optional[str] = None,
    sort_string: Optional[str] = None,
    sample: Optional[int] = None
) -> OQO:
    """
    Parse URL filter/sort strings into an OQO object.
    
    Args:
        entity_type: The entity type (e.g., "works", "authors")
        filter_string: The filter parameter value (e.g., "type:article,year:2024-")
        sort_string: The sort parameter value (e.g., "cited_by_count:desc")
        sample: Optional sample size
    
    Returns:
        OQO object representing the query
    """
    filter_rows = []
    
    if filter_string:
        filter_rows = parse_filter_string(filter_string)
    
    sort_by_column = None
    sort_by_order = None
    
    if sort_string:
        sort_by_column, sort_by_order = parse_sort_string(sort_string)
    
    return OQO(
        get_rows=entity_type,
        filter_rows=filter_rows,
        sort_by_column=sort_by_column,
        sort_by_order=sort_by_order,
        sample=sample
    )


def parse_filter_string(filter_string: str) -> List[FilterType]:
    """
    Parse a filter string into a list of filter objects.
    
    Handles:
    - Multiple filters: field1:value1,field2:value2
    - OR within values: field:value1|value2
    - Negation: field:!value
    - Ranges: field:2020-2024, field:2020-, field:-2024
    - Null: field:null, field:!null
    """
    filters = []
    
    # Split by comma, but be careful about values that might contain commas
    # We need to handle field:value pairs properly
    filter_parts = split_filter_string(filter_string)
    
    # Group filters by field to detect OR patterns
    field_groups: Dict[str, List[Tuple[str, str]]] = {}
    
    for part in filter_parts:
        if ":" not in part:
            continue
        
        # Split on first colon only (values might contain colons)
        colon_idx = part.index(":")
        field = part[:colon_idx]
        value = part[colon_idx + 1:]
        
        if field not in field_groups:
            field_groups[field] = []
        field_groups[field].append((field, value))
    
    # Process each field group
    for field, pairs in field_groups.items():
        field_filters = []
        
        for _, value in pairs:
            parsed = parse_single_filter(field, value)
            if isinstance(parsed, list):
                field_filters.extend(parsed)
            else:
                field_filters.append(parsed)
        
        filters.extend(field_filters)
    
    return filters


def split_filter_string(filter_string: str) -> List[str]:
    """
    Split a filter string by commas, but respect quoted strings.
    Commas inside double quotes are not treated as separators.

    Example:
        'type:article,raw_affiliation_strings.search:"Dept of Chemistry, UCLA"'
        -> ['type:article', 'raw_affiliation_strings.search:"Dept of Chemistry, UCLA"']
    """
    parts = []
    current = ""
    in_quotes = False

    for char in filter_string:
        if char == '"':
            in_quotes = not in_quotes
            current += char
        elif char == "," and not in_quotes:
            if current:
                parts.append(current)
            current = ""
        else:
            current += char

    if current:
        parts.append(current)

    return parts


def parse_single_filter(field: str, value: str) -> FilterType:
    """
    Parse a single field:value pair into filter object(s).
    
    Handles:
    - OR: value1|value2 -> BranchFilter with join="or"
    - Negation: !value -> operator="is not"
    - Ranges: 2020-2024, 2020-, -2024
    - Null: null, !null
    """
    # Handle OR (pipe) in values
    if "|" in value:
        return parse_or_values(field, value)
    
    # Handle null
    if value == "null":
        return LeafFilter(column_id=field, value=None, operator="is")
    
    if value == "!null":
        return LeafFilter(column_id=field, value=None, operator="is not")
    
    # Handle negation
    if value.startswith("!"):
        actual_value = value[1:]
        return LeafFilter(column_id=field, value=actual_value, operator="is not")
    
    # Handle ranges
    range_filter = parse_range_value(field, value)
    if range_filter:
        return range_filter
    
    # Simple value
    return LeafFilter(column_id=field, value=value, operator="is")


def parse_or_values(field: str, value: str) -> FilterType:
    """
    Parse OR values (pipe-separated) into a BranchFilter.
    
    Example: type:article|book -> BranchFilter(join="or", filters=[...])
    """
    parts = value.split("|")
    
    # Check if all values are negated
    all_negated = all(p.startswith("!") for p in parts)
    
    filters = []
    for part in parts:
        if part.startswith("!"):
            filters.append(LeafFilter(
                column_id=field, 
                value=part[1:], 
                operator="is not"
            ))
        else:
            filters.append(LeafFilter(
                column_id=field, 
                value=part, 
                operator="is"
            ))
    
    return BranchFilter(join="or", filters=filters)


def parse_range_value(field: str, value: str) -> Optional[FilterType]:
    """
    Parse range values into filter(s).
    
    Patterns:
    - 2020-2024 -> >= 2020 AND <= 2024 (two filters)
    - 2020- -> >= 2020
    - -2024 -> <= 2024
    """
    # Check for range pattern: value-value
    # But be careful: negative numbers like -5 should not be treated as ranges
    # And ISO dates like 2024-01-15 should be exact matches
    
    # Pattern: ends with dash (e.g., 2020-)
    if value.endswith("-") and not value.startswith("-"):
        start_value = value[:-1]
        return LeafFilter(column_id=field, value=start_value, operator=">=")
    
    # Pattern: starts with dash (e.g., -2024) but not a negative number in a range
    if value.startswith("-") and not is_date_or_number_range(value):
        end_value = value[1:]
        return LeafFilter(column_id=field, value=end_value, operator="<=")
    
    # Pattern: range with both bounds (e.g., 2020-2024)
    # We need to distinguish from dates (2024-01-15)
    if "-" in value and is_range_pattern(value):
        # Split on dash, but handle potential date values
        return parse_bounded_range(field, value)
    
    return None


def is_date_or_number_range(value: str) -> bool:
    """Check if value looks like a date or simple number (not a range)."""
    # ISO date pattern
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    # Negative number
    if re.match(r"^-\d+\.?\d*$", value):
        return False
    return True


def is_range_pattern(value: str) -> bool:
    """
    Check if value looks like a range pattern (start-end).
    
    Examples that ARE ranges: 2020-2024, 100-500
    Examples that are NOT ranges: 2024-01-15 (date), -100 (negative number)
    """
    # ISO date - not a range
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    
    # Simple number range: digits-digits
    if re.match(r"^\d+\.?\d*-\d+\.?\d*$", value):
        return True
    
    # Year range (4-digit years)
    if re.match(r"^\d{4}-\d{4}$", value):
        return True
    
    return False


def parse_bounded_range(field: str, value: str) -> List[LeafFilter]:
    """
    Parse a bounded range (e.g., 2020-2024) into two filters.
    Returns a list because this is AND logic (>= start AND <= end).
    """
    # For simple numeric ranges
    if re.match(r"^\d+\.?\d*-\d+\.?\d*$", value):
        parts = value.split("-")
        start_value = parts[0]
        end_value = parts[1]
        
        return [
            LeafFilter(column_id=field, value=start_value, operator=">="),
            LeafFilter(column_id=field, value=end_value, operator="<=")
        ]
    
    # For year ranges
    if re.match(r"^\d{4}-\d{4}$", value):
        parts = value.split("-")
        return [
            LeafFilter(column_id=field, value=parts[0], operator=">="),
            LeafFilter(column_id=field, value=parts[1], operator="<=")
        ]
    
    # Default: treat as exact match
    return [LeafFilter(column_id=field, value=value, operator="is")]


def parse_sort_string(sort_string: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a sort string into column and order.
    
    Example: "cited_by_count:desc" -> ("cited_by_count", "desc")
    """
    if ":" in sort_string:
        parts = sort_string.split(":")
        return parts[0], parts[1] if len(parts) > 1 else "desc"
    
    # Default to desc if no order specified
    return sort_string, "desc"
