"""
URL Parser - Converts URL filter strings to OQO format.

Handles the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, GroupBy, SortBy


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
    search_string: Optional[str] = None,
    semantic_search_string: Optional[str] = None,
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
        search_string: Optional top-level `?search=` value. Legacy maps a bare
            `?search=X` to the same internal scope as `filter=default.search:X`
            (`core/params.py:96-98`, scope `("default", None)`), so it AND's a
            `default.search` contains-filter into the OQO. Routed through
            `parse_single_filter` (NOT the comma-splitting filter-string parser)
            so a free-text value containing commas stays one search clause; this
            also gives `.search` columns the `contains` operator and Lucene
            boolean lifting for free.
        semantic_search_string: Optional top-level `?search.semantic=` value. The
            engine exposes two-phase vector search ONLY as this param — there is
            no `filter=…search.semantic:` form (core/vector_index.py refuses to
            combine it with a filter) — and it is field-less (whole-document). It
            maps to the canonical OQL semantic surface `abstract is similar to
            "…"` → a `LeafFilter("abstract.search.semantic", value, "contains")`
            (spec §search-modes, corpus row 30). Inverse of the
            `render_oqo_to_url` semantic-routing branch, so a working prod
            `?search.semantic=` URL round-trips to OQL.

    Returns:
        OQO object representing the query
    """
    filter_rows = []

    if path_id:
        filter_rows.append(LeafFilter(column_id="ids.openalex", value=path_id))

    if filter_string:
        filter_rows.extend(parse_filter_string(filter_string, entity_type))

    if search_string:
        parsed_search = parse_single_filter(
            "default.search", search_string, entity_type
        )
        if isinstance(parsed_search, list):
            filter_rows.extend(parsed_search)
        else:
            filter_rows.append(parsed_search)

    if semantic_search_string:
        filter_rows.append(
            LeafFilter(
                column_id="abstract.search.semantic",
                value=semantic_search_string,
                operator="contains",
            )
        )

    sort_by = []
    if sort_string:
        sort_by = parse_sort_string(sort_string)

    group_by = []
    if group_by_string:
        group_by = parse_group_by_string(group_by_string)

    select = parse_select_string(select_string) if select_string else []

    return OQO(
        get_rows=entity_type,
        filter_rows=filter_rows,
        sort_by=sort_by,
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


def parse_filter_string(
    filter_string: str, entity_type: Optional[str] = None
) -> List[FilterType]:
    """
    Parse a filter string into a list of filter objects.

    Handles:
    - Multiple filters: field1:value1,field2:value2
    - OR within values: field:value1|value2
    - Negation: field:!value
    - Ranges: field:2020-2024, field:2020-, field:-2024
    - Null: field:null, field:!null

    `entity_type` (the OQO `get_rows`) enables column-type-aware range parsing:
    a hyphen is only treated as a range separator on numeric/date columns. Pass
    None (legacy direct callers) to keep purely value-shape-based range parsing.
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
        # A value that ALREADY starts with a quote is itself the inline quoted form
        # (a phrase, single-phrase proximity `"a b"~3`, or binary `"a"~3~"b"`) — don't
        # re-wrap it, which would double-quote and corrupt it (oxjob #355).
        if field.endswith(".search.exact"):
            field = field[: -len(".exact")]
            if not value.startswith('"'):
                value = f'"{value}"'

        if field not in field_groups:
            field_groups[field] = []
        field_groups[field].append((field, value))
    
    # Process each field group
    for field, pairs in field_groups.items():
        field_filters = []
        
        for _, value in pairs:
            parsed = parse_single_filter(field, value, entity_type)
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


def parse_single_filter(
    field: str, value: str, entity_type: Optional[str] = None
) -> FilterType:
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
    range_filter = parse_range_value(field, value, entity_type)
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

    # A leading "!" negates the WHOLE OR-list: `!a|b|c` means NOT (a OR b OR c),
    # not `(NOT a) OR b OR c`. Legacy core/filter.py:92 ("negate everything in
    # values after !") ANDs the per-value negations and rejects "!" on any
    # non-leading element. Mirror that: strip "!" from every part, build a positive
    # OR-branch, and negate the branch (the canonicalizer pushes the NOT down via
    # De Morgan). Without this the OQO over-counts wildly — `(NOT a) OR …` ≈ the
    # whole index (#323 Pattern D negated OR-list).
    if value.startswith("!"):
        filters = [
            LeafFilter(column_id=field, value=part.lstrip("!"), operator=default_op)
            for part in parts
        ]
        return BranchFilter(join="or", filters=filters, is_negated=True)

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


def _should_range_parse(entity_type: Optional[str], field: str) -> bool:
    """Whether a hyphen in `field`'s value should be read as a range separator.

    Range-ness is a *column-type* property, not a value-shape one: legacy only
    range-parses numeric/date columns (`RangeField`/`DateField`). String/term
    columns whose values legitimately contain hyphens — most importantly ISSN
    (`NNNN-NNNN`), but also any other `TermField` ID — must keep the hyphen as
    part of an exact value, never split it into `>=a AND <=b`.

    We consult the entity-property catalog (the same source the validator uses).
    To stay a strictly *narrowing* fix (no regression), we only suppress
    range-parsing when we can positively confirm the property exists and lacks a
    range operator:
    - `entity_type` is None (direct callers w/o entity context) -> keep old behavior
    - property not found in the catalog -> keep old behavior (validator flags it)
    - property found and supports `range`/`date_range` -> range-parse
    - property found and does NOT -> exact match (the fix)
    """
    if entity_type is None:
        return True
    from core.properties import get_property

    prop = get_property(entity_type, field)
    if prop is None:
        return True
    operators = prop.operators or []
    return "range" in operators or "date_range" in operators


def parse_range_value(
    field: str, value: str, entity_type: Optional[str] = None
) -> Optional[FilterType]:
    """
    Parse range values into filter(s).

    Patterns:
    - 2020-2024 -> >= 2020 AND <= 2024 (two filters)
    - 2020- -> >= 2020
    - -2024 -> <= 2024

    Range-parsing is gated on column type (see `_should_range_parse`): for a
    non-range column (e.g. ISSN) this returns None so the caller falls through
    to an exact-match LeafFilter.
    """
    # Range-ness is a column property, not a value shape: e.g. `issn:0021-9258`
    # is an exact ISSN, not the range >=0021 AND <=9258.
    if not _should_range_parse(entity_type, field):
        return None

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
        # Quoted phrase, with optional proximity suffix `"phrase"~3`, or binary
        # proximity `"A"~3~"B"` (two operands NEAR each other — oxjob #355 Goal B).
        if ch == '"':
            j = i + 1
            while j < n and value[j] != '"':
                j += 1
            j = min(j + 1, n)  # include closing quote
            # Optional proximity suffix `~N`
            if j < n and value[j] == "~":
                k = j + 1
                while k < n and value[k].isdigit():
                    k += 1
                # Binary proximity: a second `~"phrase"` operand stays in this token,
                # so `"A"~3~"B"` is ONE PHRASE (else `~` and `"B"` split off and AND).
                if k + 1 < n and value[k] == "~" and value[k + 1] == '"':
                    k += 2
                    while k < n and value[k] != '"':
                        k += 1
                    k = min(k + 1, n)
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


def parse_sort_string(sort_string: str) -> List[SortBy]:
    """
    Parse a (possibly multi-column) sort string into an ordered list of SortBy.

    A legacy `sort=` URL param is a comma-separated list of `column[:direction]`
    keys applied in order as primary/secondary/… tiebreakers, e.g.
    `sort=publication_year:desc,cited_by_count:desc` ->
    [SortBy("publication_year","desc"), SortBy("cited_by_count","desc")].

    Each key defaults to "asc" when no direction is given, to match the legacy
    URL path: core/utils.py:map_sort_params assigns "asc" for a directionless
    sort. A desc default here silently reversed the page vs legacy (#323
    Pattern F1). Blank segments (e.g. a trailing comma) are skipped.
    """
    sort_by = []
    for segment in sort_string.split(","):
        segment = segment.strip()
        if not segment:
            continue
        if ":" in segment:
            parts = segment.split(":")
            column = parts[0]
            direction = parts[1] if len(parts) > 1 and parts[1] else "asc"
        else:
            column = segment
            direction = "asc"
        sort_by.append(SortBy(column_id=column, direction=direction))
    return sort_by
