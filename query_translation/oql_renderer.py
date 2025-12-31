"""
OQL Renderer - Converts OQO format to OQL (human-readable query language).

Generates plain text OQL strings like:
  Works where publication_year >= 2020 and type is article; sort by cited_by_count desc;
"""

from typing import Optional
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


def render_oqo_to_oql(oqo: OQO) -> str:
    """
    Render an OQO object to OQL format.
    
    Args:
        oqo: The OQO object to render
    
    Returns:
        OQL string representation
    """
    parts = []
    
    # Entity name (capitalized)
    entity_name = oqo.get_rows.replace("-", " ").title()
    parts.append(entity_name)
    
    # Filters
    if oqo.filter_rows:
        parts.append(" where ")
        filter_clauses = []
        for f in oqo.filter_rows:
            clause = render_filter(f)
            if clause:
                filter_clauses.append(clause)
        parts.append(" and ".join(filter_clauses))
    
    # Sort
    if oqo.sort_by_column:
        order = oqo.sort_by_order or "desc"
        parts.append(f"; sort by {oqo.sort_by_column} {order}")
    
    # Sample
    if oqo.sample:
        parts.append(f"; sample {oqo.sample}")
    
    return "".join(parts)


def render_filter(f: FilterType) -> str:
    """Render a single filter to OQL."""
    if isinstance(f, LeafFilter):
        return render_leaf_filter(f)
    elif isinstance(f, BranchFilter):
        return render_branch_filter(f)
    return ""


def render_leaf_filter(f: LeafFilter) -> str:
    """
    Render a leaf filter to OQL.
    
    Examples:
    - publication_year is 2024
    - type is not article
    - cited_by_count >= 100
    - title.search contains "machine learning"
    """
    column = f.column_id
    value = f.value
    operator = f.operator
    
    # Format value
    if value is None:
        value_str = "null"
    elif isinstance(value, bool):
        value_str = str(value).lower()
    elif isinstance(value, str):
        # Quote strings that contain spaces or special characters
        if " " in value or "," in value:
            value_str = f'"{value}"'
        else:
            value_str = value
    else:
        value_str = str(value)
    
    # Format operator
    if operator == "is":
        return f"{column} is {value_str}"
    elif operator == "is not":
        return f"{column} is not {value_str}"
    elif operator == ">=":
        return f"{column} >= {value_str}"
    elif operator == "<=":
        return f"{column} <= {value_str}"
    elif operator == ">":
        return f"{column} > {value_str}"
    elif operator == "<":
        return f"{column} < {value_str}"
    elif operator == "contains":
        return f"{column} contains {value_str}"
    elif operator == "does not contain":
        return f"{column} does not contain {value_str}"
    else:
        return f"{column} {operator} {value_str}"


def render_branch_filter(f: BranchFilter) -> str:
    """
    Render a branch filter to OQL.
    
    Example: (type is article or type is book)
    """
    if not f.filters:
        return ""
    
    sub_clauses = []
    for sub_f in f.filters:
        clause = render_filter(sub_f)
        if clause:
            sub_clauses.append(clause)
    
    if not sub_clauses:
        return ""
    
    if len(sub_clauses) == 1:
        return sub_clauses[0]
    
    join_word = f" {f.join} "
    joined = join_word.join(sub_clauses)
    
    # Wrap in parentheses for clarity
    return f"({joined})"
