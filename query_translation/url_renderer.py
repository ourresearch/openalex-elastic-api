"""
URL Renderer - Converts OQO format to URL filter strings.

Generates the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, SortBy

# K-ary list proximity `"a"~N~"b"~"c"[...]` (3+ operands, oxjob #514) — an OQL-only
# capability. The classic URL `~` syntax expresses single (`"P"~N`) and binary
# (`"A"~N~"B"`) proximity only; a 3+-operand value has no URL form, so it renders as
# `oql-only` (URLRenderError) rather than a string the frozen URL parser can't read back.
_KARY_PROXIMITY_RE = re.compile(r'^"[^"]*"~\d+(?:~"[^"]*"){2,}$')


class URLRenderError(Exception):
    """Raised when OQO cannot be converted to URL format."""
    pass


SEMANTIC_SUFFIX = ".search.semantic"


def render_oqo_to_url(oqo: OQO) -> Dict[str, Any]:
    """
    Render an OQO object to URL format.

    Args:
        oqo: The OQO object to render

    Returns:
        Dict with 'filter', 'search.semantic', 'sort', 'sample', 'group_by',
        and (logistics layer, #318) 'select', 'seed', 'per_page', 'page',
        'cursor' keys.

    Raises:
        URLRenderError: If the OQO contains structures that cannot be
                       expressed in URL format (e.g., nested boolean logic)
    """
    # Corpus selection (#481) has no classic OXURL form — the legacy
    # `include_xpac` param is on #464's drop list and a `?filter=is_xpac:` form
    # is being retired — so a non-core corpus is OQL-only. Raise rather than
    # silently render a URL that drops the corpus (which would mislead callers
    # into thinking the URL is a faithful equivalent).
    if getattr(oqo, "corpus", "core") and oqo.corpus != "core":
        raise URLRenderError(
            f"corpus '{oqo.corpus}' cannot be expressed as a classic OpenAlex "
            "URL; it is OQL-only (use the OQL corpus selector, e.g. "
            "'works (all corpora) …')"
        )

    # Semantic search (`<field> is similar to "..."`) is lifted OUT of the
    # `filter=` string into its own top-level `search.semantic=` param — the
    # engine exposes vector search only that way (see _extract_semantic).
    semantic_value, filter_rows = _extract_semantic(oqo.filter_rows)
    filter_string = render_filters(filter_rows)
    sort_string = render_sort(oqo.sort_by)
    group_by_string = render_group_by(oqo.group_by)
    select_string = render_select(oqo.select)

    return {
        "filter": filter_string if filter_string else None,
        "search.semantic": semantic_value,
        "sort": sort_string if sort_string else None,
        "sample": oqo.sample,
        "group_by": group_by_string if group_by_string else None,
        # Logistics layer (#318) — column order preserved; pagination/seed are
        # bare transport params.
        "select": select_string if select_string else None,
        "seed": oqo.seed,
        "per_page": oqo.per_page,
        "page": oqo.page,
        "cursor": oqo.cursor,
    }


def _is_semantic_leaf(f: FilterType) -> bool:
    return (
        isinstance(f, LeafFilter)
        and isinstance(f.column_id, str)
        and f.column_id.endswith(SEMANTIC_SUFFIX)
    )


def _reject_nested_semantic(f: FilterType) -> None:
    """A semantic leaf buried inside a boolean branch can't become the single
    top-level `search.semantic=` param — flag it rather than silently dropping
    it into a `filter=` clause the engine would reject."""
    if isinstance(f, BranchFilter):
        for sub in f.filters:
            if _is_semantic_leaf(sub):
                raise URLRenderError(
                    "Semantic search nested in boolean logic cannot be "
                    "expressed in URL format"
                )
            _reject_nested_semantic(sub)


def _extract_semantic(filters: List[FilterType]) -> Tuple[Optional[str], List[FilterType]]:
    """Lift a top-level semantic-search leaf out of the filter list.

    Semantic search (`<field> is similar to "..."`, OQO column
    `*.search.semantic`) is a two-phase vector search the engine exposes ONLY as
    the top-level `?search.semantic=` param — there is no `filter=…search.semantic:`
    form (core/vector_index.py refuses to combine `search.semantic` with a filter
    clause). So it must be pulled out of the comma-joined `filter=` string into its
    own param, or any rendered URL would silently not run a vector search.

    Returns (semantic_value or None, remaining_filters). Raises URLRenderError for
    shapes the single top-level param can't carry: a negated semantic clause, more
    than one semantic clause, or a semantic leaf nested in a boolean branch.
    """
    semantic_values = []
    remaining = []
    for f in filters:
        if _is_semantic_leaf(f):
            if getattr(f, "is_negated", False):
                raise URLRenderError(
                    "Negated semantic search cannot be expressed in URL format"
                )
            semantic_values.append(str(f.value))
        else:
            _reject_nested_semantic(f)
            remaining.append(f)

    if len(semantic_values) > 1:
        raise URLRenderError(
            "Only one semantic search clause can be expressed in URL format"
        )
    return (semantic_values[0] if semantic_values else None), remaining


def render_select(select) -> Optional[str]:
    """Render a list of select fields to `col1,col2` URL form.

    Column order is meaningful (display order) and preserved.
    """
    if not select:
        return None
    return ",".join(select)


def render_group_by(group_by) -> Optional[str]:
    """Render a list of GroupBy dimensions to `col1,col2` URL form.

    Dimension order is meaningful (spec §8) and preserved.
    """
    if not group_by:
        return None
    return ",".join(g.column_id for g in group_by)


def render_filters(filters: List[FilterType]) -> Optional[str]:
    """
    Render a list of filters to URL filter string.

    Top-level filters are AND-ed (joined by comma).
    """
    if not filters:
        return None

    # Collapse a `>=a` + `<=b` pair on the same column into one inclusive-range
    # clause `col:a-b` (oxjob #378 S4). The OQO canonicalizer represents a bounded
    # range as two leaves; without this, meta.x_query.url shows two clauses and the
    # GUI hydrates two bound chips instead of one range chip (#378 V1 gate).
    collapsed_range_at, consumed = _bounded_range_collapse(filters)

    parts = []
    for i, f in enumerate(filters):
        if i in collapsed_range_at:
            parts.append(collapsed_range_at[i])
        elif i in consumed:
            continue  # the other half of an already-emitted collapsed range
        else:
            rendered = render_single_filter(f)
            if rendered:
                parts.append(rendered)

    return ",".join(parts) if parts else None


def _bounded_range_collapse(filters: List[FilterType]):
    """Find same-column inclusive-bound pairs (`>=a` and `<=b`) among the top-level
    leaves and pre-render each as a single `col:a-b` clause.

    Returns (collapsed_range_at, consumed):
      - collapsed_range_at: {anchor_index: "col:a-b"} — the merged clause is emitted
        at the position of whichever bound came first (order otherwise preserved).
      - consumed: set of indices whose leaf was folded into a merged clause.

    Only non-negated inclusive bounds (>=, <=) with non-null values collapse —
    strict >/< (rendered `>a`/`<b`) and open-ended single bounds are left untouched,
    so `col:a-b` keeps its exact oxurl meaning (`>=a AND <=b`). Round-trips faithfully:
    `a-b` parses back to the same two leaves.
    """
    GE_OPS = (">=", "is greater than or equal to")
    LE_OPS = ("<=", "is less than or equal to")
    ge, le = {}, {}
    for i, f in enumerate(filters):
        if not isinstance(f, LeafFilter) or f.is_negated or f.value is None:
            continue
        if f.operator in GE_OPS:
            ge.setdefault(f.column_id, (i, f.value))
        elif f.operator in LE_OPS:
            le.setdefault(f.column_id, (i, f.value))

    collapsed_range_at, consumed = {}, set()
    for col, (gi, gv) in ge.items():
        if col not in le:
            continue
        li, lv = le[col]
        anchor = min(gi, li)
        collapsed_range_at[anchor] = f"{col}:{gv}-{lv}"
        consumed.add(gi)
        consumed.add(li)
    return collapsed_range_at, consumed


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
    - is_negated: field:!value
    - >=: field:value-
    - <=: field:-value
    - null: field:null
    """
    field = f.column_id
    value = f.value
    operator = f.operator
    negated = bool(f.is_negated)

    # Handle null values
    if value is None:
        if negated:
            return f"{field}:!null"
        return f"{field}:null"

    # Convert value to string
    str_value = str(value).lower() if isinstance(value, bool) else str(value)

    # K-ary list proximity (3+ operands) is OQL-only — no classic URL `~` form (#514).
    if isinstance(value, str) and _KARY_PROXIMITY_RE.match(value):
        raise URLRenderError(
            "K-ary list proximity (3+ operands) has no classic URL form; the `~` "
            "syntax expresses single and binary proximity only"
        )

    # Negation is the polarity bit: render as bang-prefixed value
    if negated:
        return f"{field}:!{str_value}"

    # Handle operators
    if operator in (">=", "is greater than or equal to"):
        return f"{field}:{str_value}-"
    elif operator in ("<=", "is less than or equal to"):
        return f"{field}:-{str_value}"
    elif operator in (">", "is greater than"):
        return f"{field}:>{str_value}"
    elif operator in ("<", "is less than"):
        return f"{field}:<{str_value}"
    elif operator in ("has", "includes"):
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
        # A null-sentinel leaf (`language is (en or unknown)`, #554) renders as
        # the classic URL's `null` token, same as the standalone-leaf path.
        val = "null" if sub_f.value is None else str(sub_f.value)
        if getattr(sub_f, "is_negated", False):
            values.append(f"!{val}")
        else:
            values.append(val)

    pipe_joined = "|".join(values)
    return f"{field}:{pipe_joined}"


def render_sort(sort_by: List[SortBy]) -> Optional[str]:
    """Render the ordered sort-key list to a URL `sort=` string.

    Emits a comma-separated `column:direction` list preserving the tiebreaker
    order, e.g. [pub_year:desc, cited_by_count:desc] ->
    "publication_year:desc,cited_by_count:desc". Direction is always rendered
    explicitly so the string round-trips back to the same SortBy list.

    A metric-aggregate group sort (oxjob #389) round-trips through the dotted
    pseudo-field form `<column>.<aggregate>:<direction>`, e.g.
    `cited_by_count.mean:desc`, so `parse_sort_string` re-derives the same SortBy.
    """
    if not sort_by:
        return None

    def _render_one(s: SortBy) -> str:
        column = f"{s.column_id}.{s.aggregate}" if s.aggregate else s.column_id
        return f"{column}:{s.direction or 'asc'}"

    return ",".join(_render_one(s) for s in sort_by)


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
        # A semantic leaf becomes the top-level `search.semantic=` param, which
        # has no negated form (see _extract_semantic). Negated is the only leaf
        # shape that can't render; a plain semantic leaf is fine.
        if _is_semantic_leaf(f) and getattr(f, "is_negated", False):
            raise URLRenderError(
                "Negated semantic search cannot be expressed in URL format"
            )
        return  # other leaf filters are always expressible

    if isinstance(f, BranchFilter):
        # A semantic clause must stand alone as the top-level param; nested in a
        # boolean branch it can't be expressed.
        _reject_nested_semantic(f)

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
