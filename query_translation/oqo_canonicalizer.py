"""
OQO Canonicalizer - Normalizes OQO for deterministic output.

Canonicalization ensures:
1. Typed values (int vs "int", bool vs "bool")
2. Normalized entity IDs (lowercase, proper format)
3. Flattened redundant AND groups
4. Eliminated single-child groups
5. Stable output for reliable tests

See oql-oqo-plan.md Section 4 for canonicalization rules.
"""

from typing import List, Union, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


def canonicalize_oqo(oqo: OQO) -> OQO:
    """
    Canonicalize an OQO object for deterministic output.
    
    Args:
        oqo: The OQO object to canonicalize
    
    Returns:
        A new canonicalized OQO object
    """
    canonical_filters = []
    for f in oqo.filter_rows:
        canonical_f = canonicalize_filter(f)
        if canonical_f is not None:
            # Flatten if we get a single-child result that should be unwrapped
            if isinstance(canonical_f, list):
                canonical_filters.extend(canonical_f)
            else:
                canonical_filters.append(canonical_f)
    
    return OQO(
        get_rows=oqo.get_rows.lower(),  # Normalize entity type to lowercase
        filter_rows=canonical_filters,
        sort_by_column=oqo.sort_by_column,
        sort_by_order=oqo.sort_by_order,
        sample=oqo.sample
    )


def canonicalize_filter(f: FilterType) -> Union[FilterType, List[FilterType], None]:
    """
    Canonicalize a single filter.
    
    Returns:
        - A canonicalized filter
        - A list of filters (if a group was flattened)
        - None (if filter should be removed)
    """
    if isinstance(f, LeafFilter):
        return canonicalize_leaf_filter(f)
    elif isinstance(f, BranchFilter):
        return canonicalize_branch_filter(f)
    return None


def canonicalize_leaf_filter(f: LeafFilter) -> LeafFilter:
    """
    Canonicalize a leaf filter.
    
    - Normalizes value types (string "true" -> bool True)
    - Normalizes entity IDs
    """
    value = canonicalize_value(f.value, f.column_id)
    operator = f.operator or "is"
    
    return LeafFilter(
        column_id=f.column_id,
        value=value,
        operator=operator
    )


def canonicalize_value(value: Any, column_id: str) -> Any:
    """
    Canonicalize a filter value.
    
    - Convert string booleans to actual booleans for boolean columns
    - Convert string integers to actual integers for numeric columns
    - Normalize entity ID format
    """
    if value is None:
        return None
    
    # Boolean normalization
    if isinstance(value, str):
        lower_val = value.lower()
        if lower_val == "true":
            return True
        if lower_val == "false":
            return False
    
    # Integer normalization for known numeric columns
    if isinstance(value, str) and column_id in NUMERIC_COLUMNS:
        try:
            # Check if it's an integer
            if "." not in value:
                return int(value)
            else:
                return float(value)
        except ValueError:
            pass
    
    # Entity ID normalization
    if isinstance(value, str) and "/" in value:
        return normalize_entity_id(value)
    
    return value


def normalize_entity_id(entity_id: str) -> str:
    """
    Normalize an entity ID to canonical format.
    
    Examples:
        - "Countries/CA" -> "countries/ca"
        - "institutions/I123" -> "institutions/I123" (preserve case for OpenAlex IDs)
        - "types/Article" -> "types/article"
    """
    if "/" not in entity_id:
        return entity_id
    
    parts = entity_id.split("/", 1)
    entity_type = parts[0].lower()
    short_id = parts[1]
    
    # Preserve case for OpenAlex IDs (start with letter followed by numbers)
    # Otherwise lowercase
    if not (len(short_id) > 1 and short_id[0].isalpha() and short_id[1:].isdigit()):
        short_id = short_id.lower()
    
    return f"{entity_type}/{short_id}"


def canonicalize_branch_filter(f: BranchFilter) -> Union[FilterType, List[FilterType], None]:
    """
    Canonicalize a branch filter.
    
    Rules:
    1. Recursively canonicalize children
    2. Remove empty children
    3. Flatten single-child groups
    4. Flatten nested same-join groups (AND inside AND)
    """
    canonical_children: List[FilterType] = []
    
    for child in f.filters:
        canonical_child = canonicalize_filter(child)
        if canonical_child is None:
            continue
        
        if isinstance(canonical_child, list):
            canonical_children.extend(canonical_child)
        elif isinstance(canonical_child, BranchFilter) and canonical_child.join == f.join:
            # Flatten same-join nested groups
            canonical_children.extend(canonical_child.filters)
        else:
            canonical_children.append(canonical_child)
    
    # Empty group -> None
    if not canonical_children:
        return None
    
    # Single child -> unwrap
    if len(canonical_children) == 1:
        return canonical_children[0]
    
    return BranchFilter(
        join=f.join,
        filters=canonical_children
    )


# Columns that should have numeric values
NUMERIC_COLUMNS = {
    "publication_year",
    "cited_by_count",
    "fwci",
    "cited_by_percentile_year.min",
    "cited_by_percentile_year.max",
    "works_count",
    "h_index",
    "i10_index",
    "2yr_mean_citedness",
}
