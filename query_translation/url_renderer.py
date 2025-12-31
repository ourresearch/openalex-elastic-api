"""
URL Renderer - Converts OQO format to URL filter strings.

Generates the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


class URLRenderError(Exception):
    """Raised when OQO cannot be converted to URL format."""
    pass


def render_oqo_to_url(oqo: OQO) -> Dict[str, Any]:
    """
    Render an OQO object to URL format.
    
    Args:
        oqo: The OQO object to render
    
    Returns:
        Dict with 'filter', 'sort', and 'sample' keys
    
    Raises:
        URLRenderError: If the OQO contains structures that cannot be
                       expressed in URL format (e.g., nested boolean logic)
    """
    filter_string = render_filters(oqo.filter_rows)
    sort_string = render_sort(oqo.sort_by_column, oqo.sort_by_order)
    
    return {
        "filter": filter_string if filter_string else None,
        "sort": sort_string if sort_string else None,
        "sample": oqo.sample
    }


def render_filters(filters: List[FilterType]) -> Optional[str]:
    """
    Render a list of filters to URL filter string.
    
    Top-level filters are AND-ed (joined by comma).
    """
    if not filters:
        return None
    
    parts = []
    
    for f in filters:
        rendered = render_single_filter(f)
        if rendered:
            parts.append(rendered)
    
    return ",".join(parts) if parts else None


def render_single_filter(f: FilterType, depth: int = 0) -> str:
    """
    Render a single filter to URL format.
    
    Handles:
    - LeafFilter: field:value
    - BranchFilter with OR: field:value1|value2 (only if same field)
    """
    if isinstance(f, LeafFilter):
        return render_leaf_filter(f)
    elif isinstance(f, BranchFilter):
        return render_branch_filter(f, depth)
    else:
        raise URLRenderError(f"Unknown filter type: {type(f)}")


def render_leaf_filter(f: LeafFilter) -> str:
    """
    Render a leaf filter to URL format.
    
    Examples:
    - is: field:value
    - is not: field:!value
    - >=: field:value-
    - <=: field:-value
    - null: field:null
    """
    field = f.column_id
    value = f.value
    operator = f.operator
    
    # Handle null values
    if value is None:
        if operator == "is not":
            return f"{field}:!null"
        return f"{field}:null"
    
    # Convert value to string
    str_value = str(value).lower() if isinstance(value, bool) else str(value)
    
    # Handle operators
    if operator == "is not":
        return f"{field}:!{str_value}"
    elif operator in (">=", "is greater than or equal to"):
        return f"{field}:{str_value}-"
    elif operator in ("<=", "is less than or equal to"):
        return f"{field}:-{str_value}"
    elif operator in (">", "is greater than"):
        return f"{field}:>{str_value}"
    elif operator in ("<", "is less than"):
        return f"{field}:<{str_value}"
    elif operator in ("contains", "includes"):
        # For search fields, just use the value
        return f"{field}:{str_value}"
    else:
        # Default: exact match
        return f"{field}:{str_value}"


def render_branch_filter(f: BranchFilter, depth: int = 0) -> str:
    """
    Render a branch filter to URL format.
    
    Only OR of same-field values can be expressed in URL format.
    Nested boolean logic cannot be expressed.
    """
    if f.join == "or":
        return render_or_branch(f)
    else:
        # AND branches at top level are handled by comma separation
        # Nested AND requires special handling
        if depth > 0:
            raise URLRenderError(
                "Nested AND logic cannot be expressed in URL format"
            )
        
        # Render each filter in the AND branch
        parts = []
        for sub_filter in f.filters:
            rendered = render_single_filter(sub_filter, depth + 1)
            parts.append(rendered)
        return ",".join(parts)


def render_or_branch(f: BranchFilter) -> str:
    """
    Render an OR branch to URL format.
    
    This only works if all filters in the branch are for the same field.
    Example: type is Article OR Book -> type:article|book
    """
    if not f.filters:
        return ""
    
    # Check that all filters are LeafFilters for the same field
    fields = set()
    for sub_f in f.filters:
        if isinstance(sub_f, BranchFilter):
            raise URLRenderError(
                "Nested boolean logic cannot be expressed in URL format"
            )
        fields.add(sub_f.column_id)
    
    if len(fields) > 1:
        raise URLRenderError(
            "OR across different fields cannot be expressed in URL format. "
            f"Fields involved: {', '.join(fields)}"
        )
    
    # All same field - render as pipe-separated values
    field = f.filters[0].column_id
    values = []
    
    for sub_f in f.filters:
        if sub_f.operator == "is not":
            values.append(f"!{sub_f.value}")
        else:
            values.append(str(sub_f.value))
    
    pipe_joined = "|".join(values)
    return f"{field}:{pipe_joined}"


def render_sort(
    sort_by_column: Optional[str], 
    sort_by_order: Optional[str]
) -> Optional[str]:
    """Render sort parameters to URL format."""
    if not sort_by_column:
        return None
    
    order = sort_by_order or "desc"
    return f"{sort_by_column}:{order}"


def can_render_to_url(oqo: OQO) -> Tuple[bool, Optional[str]]:
    """
    Check if an OQO can be rendered to URL format.
    
    Returns:
        Tuple of (can_render, error_message)
    """
    try:
        # Try to detect issues without full rendering
        for f in oqo.filter_rows:
            check_filter_expressible(f, depth=0)
        return True, None
    except URLRenderError as e:
        return False, str(e)


def check_filter_expressible(f: FilterType, depth: int = 0):
    """Check if a filter can be expressed in URL format."""
    if isinstance(f, LeafFilter):
        return  # Leaf filters are always expressible
    
    if isinstance(f, BranchFilter):
        if f.join == "and" and depth > 0:
            raise URLRenderError(
                "Nested AND logic cannot be expressed in URL format"
            )
        
        if f.join == "or":
            # Check all sub-filters are same field
            fields = set()
            for sub_f in f.filters:
                if isinstance(sub_f, BranchFilter):
                    raise URLRenderError(
                        "Nested boolean logic cannot be expressed in URL format"
                    )
                fields.add(sub_f.column_id)
            
            if len(fields) > 1:
                raise URLRenderError(
                    "OR across different fields cannot be expressed in URL format"
                )
        
        # Recursively check sub-filters
        for sub_f in f.filters:
            check_filter_expressible(sub_f, depth + 1)
