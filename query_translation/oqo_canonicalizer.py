"""
OQO Canonicalizer - Normalizes OQO into a deterministic canonical form.

The canonical form is used only where a *stable* representation is needed (cache
keys, hashing, dedup, test fixtures). It NEVER replaces the user's OQO; rendering
(OQO -> URL/OQL) preserves the user's operand order, and only invokes the
canonicalizer when something needs a hash.

Canonical form (per the #284 spec):
1. Typed leaf values (string "true" -> bool, numeric strings -> int for numeric columns)
2. **NNF (negation normal form)**: branch-level `is_negated` is pushed down to the
   leaves via De Morgan (flip and<->or, toggle child polarity), double negation
   cancels, so a canonical OQO carries `is_negated` only on leaves.
3. Flattened nested same-join groups; single-child groups unwrapped; empty groups dropped.
4. **Sorted** operands within every group and at the top level (AND/OR are commutative;
   NOT lives only on leaves after NNF), giving order-independent output.

Values are *bare* (the namespace is the column_id, resolved via the column
registry) — there is no entity-id prefix normalization. See docs/oql-spec.md.
"""

import json
from typing import List, Union, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


def canonicalize_oqo(oqo: OQO) -> OQO:
    """
    Canonicalize an OQO object into deterministic canonical form.

    Args:
        oqo: The OQO object to canonicalize

    Returns:
        A new canonicalized OQO object
    """
    canonical_filters = []
    for f in oqo.filter_rows:
        nnf_f = push_negation(f, negate=False)  # NNF first
        canonical_f = canonicalize_filter(nnf_f)
        if canonical_f is not None:
            # Flatten if we get a single-child result that should be unwrapped
            if isinstance(canonical_f, list):
                canonical_filters.extend(canonical_f)
            else:
                canonical_filters.append(canonical_f)

    # Top-level filter_rows are an implicit AND -> commutative -> sort for stability
    canonical_filters.sort(key=_sort_key)

    return OQO(
        get_rows=oqo.get_rows.lower(),  # Normalize entity type to lowercase
        filter_rows=canonical_filters,
        sort_by_column=oqo.sort_by_column,
        sort_by_order=oqo.sort_by_order,
        sample=oqo.sample,
        group_by=list(oqo.group_by),  # group_by order is meaningful (dim order) -> preserved
        # Logistics layer (#318) passes through unchanged: `select` order is
        # meaningful (display order), and pagination/seed defaults are applied
        # only at execution — canonical form leaves them absent when unset so
        # OQOs stay minimal and comparable.
        select=list(oqo.select),
        seed=oqo.seed,
        per_page=oqo.per_page,
        page=oqo.page,
        cursor=oqo.cursor,
    )


def push_negation(f: FilterType, negate: bool) -> FilterType:
    """Push negation down to the leaves (De Morgan), producing NNF.

    `negate` is the accumulated polarity from enclosing negated branches. A leaf
    ends up with `is_negated = leaf.is_negated XOR negate`; a branch flips its
    join (and<->or) and propagates the polarity when negated, then clears its own
    `is_negated` (negation now lives on the leaves).
    """
    if isinstance(f, LeafFilter):
        return LeafFilter(
            column_id=f.column_id,
            value=f.value,
            operator=f.operator,
            is_negated=bool(f.is_negated) ^ bool(negate),
        )
    if isinstance(f, BranchFilter):
        eff = bool(f.is_negated) ^ bool(negate)
        new_join = ("and" if f.join == "or" else "or") if eff else f.join
        return BranchFilter(
            join=new_join,
            filters=[push_negation(c, eff) for c in f.filters],
            is_negated=False,
        )
    return f


def _sort_key(f: FilterType) -> str:
    """Total order over filters for canonical operand sorting: the JSON of the
    filter's dict with sorted keys. Stable and deterministic across runs."""
    return json.dumps(f.to_dict(), sort_keys=True, ensure_ascii=True)


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

    - Normalizes value types (string "true" -> bool True; numeric strings -> int)
    - Preserves the `is_negated` polarity bit (already pushed to leaves by NNF)
    - Values stay *bare* (no entity-id prefix normalization)
    """
    value = canonicalize_value(f.value, f.column_id)
    operator = f.operator or "is"

    return LeafFilter(
        column_id=f.column_id,
        value=value,
        operator=operator,
        is_negated=bool(f.is_negated),
    )


def canonicalize_value(value: Any, column_id: str) -> Any:
    """
    Canonicalize a filter value.

    - Convert string booleans to actual booleans for boolean columns
    - Convert string integers to actual integers for numeric columns

    Values are *bare* — there is NO entity-id prefix normalization (the namespace
    is the column_id, resolved via the column registry). This also means values
    that legitimately contain "/" (e.g. a DOI like "10.1021/es052595+") pass
    through untouched. Type coercion here is a stopgap keyed off a hardcoded
    NUMERIC_COLUMNS set; the column registry (#294) is the eventual type authority.
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

    return value


def canonicalize_branch_filter(f: BranchFilter) -> Union[FilterType, List[FilterType], None]:
    """
    Canonicalize a branch filter.

    Rules:
    1. Recursively canonicalize children
    2. Remove empty children
    3. Flatten nested same-join groups (AND inside AND)
    4. Unwrap single-child groups
    5. **Sort** children (AND/OR are commutative; NOT lives only on leaves after NNF)

    Assumes the branch is already in NNF (branch-level negation pushed to leaves
    by `push_negation`), so `is_negated` on a BranchFilter is not expected here.
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

    # Sort operands for order-independent canonical output
    canonical_children.sort(key=_sort_key)

    return BranchFilter(
        join=f.join,
        filters=canonical_children,
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
