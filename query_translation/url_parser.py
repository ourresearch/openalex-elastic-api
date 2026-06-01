"""
URL Parser - Converts URL filter strings to OQO format.

Handles the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, GroupBy


def parse_url_to_oqo(
    entity_type: str,
    filter_string: Optional[str] = None,
    sort_string: Optional[str] = None,
    sample: Optional[int] = None,
    group_by_string: Optional[str] = None,
    path_id: Optional[str] = None,
    select_string: Optional[str] = None,
    seed: Optional[Any] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
    cursor: Optional[str] = None,
) -> OQO:
    """
    Parse URL filter/sort/group_by strings into an OQO object.

    Args:
        entity_type: The entity type (e.g., "works", "authors")
        filter_string: The filter parameter value (e.g., "type:article,year:2024-")
        sort_string: The sort parameter value (e.g., "cited_by_count:desc")
        sample: Optional sample size
        group_by_string: The group_by parameter value. Single dim
            ("primary_topic.id") or comma-separated for multi-dim
            ("primary_topic.id,publication_year"). Live API is single-dim
            (#297); spec is multi-dim — the translation impl round-trips both
            faithfully.
        path_id: Optional path-form entity id (e.g. "A5022654839" from the URL
            `/authors/A5022654839`). Translates to a leading
            `LeafFilter(column_id="ids.openalex", value=path_id)` so path-form
            single-entity lookups round-trip cleanly to the spec form.
        select_string: The `select` parameter value (e.g.
            "id,display_name,cited_by_count") → `oqo.select`. Logistics layer
            (#318): column projection.
        seed: Optional sample seed (URL `?seed=`). Only meaningful with `sample`.
        per_page: Optional page size (URL `?per-page=`).
        page: Optional offset page number (URL `?page=`). XOR with `cursor`.
        cursor: Optional cursor token (URL `?cursor=`). XOR with `page`.

    Returns:
        OQO object representing the query
    """
    filter_rows = []

    if path_id:
        filter_rows.append(LeafFilter(column_id="ids.openalex", value=path_id))

    if filter_string:
        filter_rows.extend(parse_filter_string(filter_string))

    sort_by_column = None
    sort_by_order = None

    if sort_string:
        sort_by_column, sort_by_order = parse_sort_string(sort_string)

    group_by = []
    if group_by_string:
        group_by = parse_group_by_string(group_by_string)

    select = parse_select_string(select_string) if select_string else []

    return OQO(
        get_rows=entity_type,
        filter_rows=filter_rows,
        sort_by_column=sort_by_column,
        sort_by_order=sort_by_order,
        sample=sample,
        group_by=group_by,
        select=select,
        seed=seed,
        per_page=per_page,
        page=page,
        cursor=cursor,
    )


def parse_select_string(select_string: str) -> List[str]:
    """Parse a `&select=col1,col2` URL value into a list of result-field names.

    Column order is meaningful (display order, §select) and preserved.
    """
    return [
        part.strip()
        for part in select_string.split(",")
        if part.strip()
    ]


def parse_group_by_string(group_by_string: str) -> List[GroupBy]:
    """Parse a `&group_by=col1,col2` URL value into a list of GroupBy dims.

    Dimension order is meaningful (spec §8) and preserved.
    """
    return [
        GroupBy(column_id=part.strip())
        for part in group_by_string.split(",")
        if part.strip()
    ]


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

        # `.search.exact:<v>` is the legacy URL surface for the spec's inline
        # quoted-phrase form (§3.1): rewrite to `.search` column with the
        # value double-quoted, which the parser treats as a phrase containment.
        if field.endswith(".search.exact"):
            field = field[: -len(".exact")]
            value = f'"{value}"'

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
    - Negation: !value -> is_negated=True (operator stays "is")
    - Ranges: 2020-2024, 2020-, -2024
    - Inline ops: >value, <value, >=value, <=value
    - Null: null, !null
    - Lucene boolean in `.search` values: `a AND (b OR c) NOT d`

    For `.search`-suffix columns the default operator is `contains` (free-text
    matching); for all other columns it's `is` (exact equality).
    """
    # Lucene-style boolean inside a .search value (AND/OR/NOT keywords,
    # optionally with parens) lifts to a BranchFilter tree of contains-leaves.
    # See _parse_search_boolean for grammar. A top-level AND-branch is
    # flattened into a list — outer filter_rows is itself an implicit AND, so
    # nesting an explicit AND-branch there is redundant and would diverge from
    # the corpus's canonical shape.
    if field.endswith(".search") and _SEARCH_BOOLEAN_KEYWORD_RE.search(value):
        parsed = _parse_search_boolean(field, value)
        if (
            isinstance(parsed, BranchFilter)
            and parsed.join == "and"
            and not parsed.is_negated
        ):
            return list(parsed.filters)
        return parsed

    # Handle OR (pipe) in values
    if "|" in value:
        return parse_or_values(field, value)

    default_op = _default_operator_for(field)

    # Handle null
    if value == "null":
        return LeafFilter(column_id=field, value=None, operator=default_op)

    if value == "!null":
        return LeafFilter(column_id=field, value=None, operator=default_op, is_negated=True)

    # Handle negation
    if value.startswith("!"):
        actual_value = value[1:]
        return LeafFilter(column_id=field, value=actual_value, operator=default_op, is_negated=True)

    # Handle inline comparison-operator prefixes. Order matters: `>=` / `<=`
    # are matched before the single-char `>` / `<`.
    for prefix, op in (("<=", "<="), (">=", ">="), (">", ">"), ("<", "<")):
        if value.startswith(prefix):
            return LeafFilter(column_id=field, value=value[len(prefix):], operator=op)

    # Handle ranges
    range_filter = parse_range_value(field, value)
    if range_filter:
        return range_filter

    # Simple value
    return LeafFilter(column_id=field, value=value, operator=default_op)


def _default_operator_for(field: str) -> str:
    """`.search`-suffix columns default to `contains`; everything else to `is`."""
    return "contains" if field.endswith(".search") else "is"


def parse_or_values(field: str, value: str) -> FilterType:
    """
    Parse OR values (pipe-separated) into a BranchFilter.
    
    Example: type:article|book -> BranchFilter(join="or", filters=[...])
    """
    parts = value.split("|")

    default_op = _default_operator_for(field)

    filters = []
    for part in parts:
        if part.startswith("!"):
            filters.append(LeafFilter(
                column_id=field,
                value=part[1:],
                operator=default_op,
                is_negated=True,
            ))
        else:
            filters.append(LeafFilter(
                column_id=field,
                value=part,
                operator=default_op,
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


# ---------------------------------------------------------------------------
# Lucene-style boolean parsing inside `.search` values
# ---------------------------------------------------------------------------
#
# Grammar (operator precedence: NOT > AND > OR; AND can be implicit before NOT):
#   expr     := or_term ( OR or_term )*
#   or_term  := and_unit ( AND? and_unit )*
#   and_unit := NOT and_unit | atom
#   atom     := '(' expr ')' | <phrase> | <quoted-phrase-with-optional-proximity>
#
# A `<phrase>` is any run of non-paren / non-boolean text — spaces are part of
# the phrase (so `supply chain` inside `(supply chain)` is one contains leaf,
# not AND(supply, chain)).

_SEARCH_BOOLEAN_KEYWORD_RE = re.compile(r"(?:^|\s)(AND|OR|NOT)(?=\s|\()")


def _tokenize_search_boolean(value: str) -> List[Tuple[str, str]]:
    """Tokenize a Lucene-style search value into (kind, text) tokens.

    Kinds: LPAREN, RPAREN, AND, OR, NOT, PHRASE (text run, may contain spaces).
    """
    tokens: List[Tuple[str, str]] = []
    i, n = 0, len(value)
    while i < n:
        ch = value[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(":
            tokens.append(("LPAREN", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(("RPAREN", ")"))
            i += 1
            continue
        # Quoted phrase (with optional proximity suffix like `"phrase"~3`)
        if ch == '"':
            j = i + 1
            while j < n and value[j] != '"':
                j += 1
            j = min(j + 1, n)  # include closing quote
            # Optional proximity suffix
            if j < n and value[j] == "~":
                k = j + 1
                while k < n and value[k].isdigit():
                    k += 1
                j = k
            tokens.append(("PHRASE", value[i:j]))
            i = j
            continue
        # Boolean keyword (uppercase, surrounded by word boundary)
        for kw in ("AND", "OR", "NOT"):
            end = i + len(kw)
            if (value[i:end] == kw and (end == n or not value[end].isalnum())):
                tokens.append((kw, kw))
                i = end
                break
        else:
            # Phrase: run up to next paren / boolean / quote
            j = i
            while j < n and value[j] not in '()"':
                if value[j].isspace():
                    # Lookahead: is the next non-space token a boolean keyword?
                    k = j
                    while k < n and value[k].isspace():
                        k += 1
                    if k < n and any(
                        value[k:k + len(kw)] == kw
                        and (k + len(kw) == n or not value[k + len(kw)].isalnum())
                        for kw in ("AND", "OR", "NOT")
                    ):
                        break
                    if k < n and value[k] in '()':
                        break
                j += 1
            tokens.append(("PHRASE", value[i:j].strip()))
            i = j
    return tokens


def _parse_search_boolean(field: str, value: str) -> FilterType:
    """Parse a Lucene-style boolean search value into a BranchFilter tree.

    All leaves are `LeafFilter(column_id=field, operator="contains")`.
    NOT lifts to `is_negated=True` on the wrapped leaf or branch (the
    canonicalizer pushes branch-level negation down to leaves).
    """
    tokens = _tokenize_search_boolean(value)
    pos = [0]

    def peek() -> Optional[Tuple[str, str]]:
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume() -> Tuple[str, str]:
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_atom() -> FilterType:
        tok = peek()
        if tok is None:
            return LeafFilter(column_id=field, value="", operator="contains")
        kind, text = tok
        if kind == "LPAREN":
            consume()
            inner = parse_expr()
            if peek() and peek()[0] == "RPAREN":
                consume()
            return inner
        if kind == "PHRASE":
            consume()
            # Strip surrounding double-quotes for the leaf value if it's a
            # plain quoted phrase (no proximity suffix); proximity stays literal.
            v = text
            if v.startswith('"') and v.endswith('"') and "~" not in v:
                v = v[1:-1]
            return LeafFilter(column_id=field, value=v, operator="contains")
        # Unexpected token (shouldn't happen for well-formed input)
        consume()
        return LeafFilter(column_id=field, value=text, operator="contains")

    def parse_not() -> FilterType:
        if peek() and peek()[0] == "NOT":
            consume()
            inner = parse_not()
            if isinstance(inner, LeafFilter):
                inner.is_negated = not inner.is_negated
                return inner
            # BranchFilter — toggle the polarity bit; canonicalizer pushes it down.
            inner.is_negated = not inner.is_negated
            return inner
        return parse_atom()

    def parse_and() -> FilterType:
        left = parse_not()
        operands = [left]
        while True:
            tok = peek()
            if tok is None or tok[0] in ("RPAREN", "OR"):
                break
            if tok[0] == "AND":
                consume()
            # else: implicit AND (e.g. `covid NOT pediatric`)
            operands.append(parse_not())
        return operands[0] if len(operands) == 1 else BranchFilter(join="and", filters=operands)

    def parse_expr() -> FilterType:
        left = parse_and()
        operands = [left]
        while peek() and peek()[0] == "OR":
            consume()
            operands.append(parse_and())
        return operands[0] if len(operands) == 1 else BranchFilter(join="or", filters=operands)

    result = parse_expr()
    # Top-level boolean tree: if it's an AND-branch, lift its children into the
    # caller's filter_rows list. parse_filter_string puts a single returned
    # FilterType in filter_rows; for the AND case we want them flattened.
    # (BranchFilter with join="and" at the top is fine — canonicalizer handles
    # both representations equivalently — but lifting matches the corpus shape
    # where the expected OQO has the AND-leaves as siblings in filter_rows.)
    return result


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
