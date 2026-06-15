"""
URL Parser - Converts URL filter strings to OQO format.

Handles the traditional query parameter syntax:
  filter=field1:value1,field2:value2&sort=field:order
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, GroupBy, SortBy, CURLY_DQUOTE_MAP, canonicalize_oqo_column_ids

# A Collection membership ref: `col_<base58>` (mirrors core/fields.py
# CollectionField.COLLECTION_ID_RE, `!` stripped before matching). A value of this
# shape — on the same-type `collection:` key or any cross-type `<entity-field>:col_…`
# — canonicalizes to the OQO `in collection` operator so a working prod URL round-trips
# to OQL's `is in collection` form. (oxjob #363)
_COLLECTION_ID_RE = re.compile(r"^col_[A-Za-z0-9]{1,48}$")


def fold_scoped_search_params(params: Dict[str, str]) -> Optional[str]:
    """Fold `search.<field>=` scoped-search params into filter clauses.

    Returns the new value for `params['filter']` — the existing filter string
    with each scoped-search param appended as a `<field>.search` clause — or
    `None` when there are no scoped-search params (leave `filter` untouched).
    Pure (no app context), so it's covered by the offline `tests/oql` gate.

    `search.<field>=<v>` becomes `<field>.search:<v>`. `search.<field>.exact=<v>`
    is the engine's exact-phrase scoped search: pull the trailing `.exact` off
    BEFORE appending `.search` and re-attach it in canonical order →
    `<field>.search.exact`, which the normalizer (see `_parse_filter_groups`)
    rewrites to a `<field>.search` column with a quoted (exact-phrase) value.
    Naively appending `.search` to `<field>.exact` builds `<field>.exact.search`
    — an order the normalizer never strips, so the registry rejects it as
    invalid_column (oxjob #422). Applies to every scoped field, not just
    `title_and_abstract`.
    """
    extra_filters = []
    for k, v in list(params.items()):
        if k.startswith("search.") and v:
            field = k[len("search."):]
            if field.endswith(".exact"):
                field = field[: -len(".exact")]
                extra_filters.append(f"{field}.search.exact:{v}")
            else:
                extra_filters.append(f"{field}.search:{v}")
    if not extra_filters:
        return None
    base = params.get("filter")
    # Join with a bare comma (NOT ", ") — the filter-clause splitter does not
    # trim, and the engine itself rejects a space-prefixed column, so a ", "
    # join would corrupt the folded column id to " <field>.search" (oxjob #363
    # case W3.1, scoped `search.title_and_abstract=`).
    return ",".join(([base] if base else []) + extra_filters)


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
    include_xpac: bool = False,
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
            `default.search` has-filter into the OQO. Routed through
            `parse_single_filter` (NOT the comma-splitting filter-string parser)
            so a free-text value containing commas stays one search clause; this
            also gives `.search` columns the `has` operator and Lucene
            boolean lifting for free.
        semantic_search_string: Optional top-level `?search.semantic=` value. The
            engine exposes two-phase vector search ONLY as this param — there is
            no `filter=…search.semantic:` form (core/vector_index.py refuses to
            combine it with a filter) — and it is field-less (whole-document). It
            maps to the canonical OQL semantic surface `abstract is similar to
            "…"` → a `LeafFilter("abstract.search.semantic", value, "has")`
            (spec §search-modes, corpus row 30). Inverse of the
            `render_oqo_to_url` semantic-routing branch, so a working prod
            `?search.semantic=` URL round-trips to OQL.
        include_xpac: The legacy `?include_xpac=true` corpus-expansion flag (#481
            leftover, #498). When True, the OQO carries `corpus="all"` (core +
            expansion), matching what the executor actually does with that param —
            so the canonical OQO / x_query echo is faithful instead of defaulting
            to `core`. An explicit `is_xpac:` filter still wins (it redirects to
            `corpus` in `canonicalize_oqo_column_ids`, run below, OVERRIDING this),
            mirroring the legacy precedence (explicit filter > include_xpac > core).
            Note: a non-core corpus is OQL-only on the render side — `?include_xpac`
            itself is on #464's drop list — so this is an oxurl→OQO INPUT fidelity
            fix, not a round-trippable URL form.

    Returns:
        OQO object representing the query
    """
    filter_rows = []

    if path_id:
        filter_rows.append(LeafFilter(column_id="ids.openalex", value=path_id))

    if filter_string:
        filter_rows.extend(parse_filter_string(filter_string, entity_type))

    if search_string:
        # oxjob #430: seed the HONEST per-entity broad-search column, not the
        # deprecated `default.search`. works → `fulltext.search` (byte-identical:
        # both route through full_search_query on the works index); every other
        # entity → `text.search` (the new canonical, identical behavior to the old
        # `default.search` it replaces). This stops `default.search` ever entering
        # the OQO, so OQL renders the correct word per entity and the #363
        # finding-#8 round-trip break ("full text contains …" on non-works) is
        # fixed at the source. `default.search` stays an accepted alternate key.
        search_column = (
            "fulltext.search"
            if (entity_type or "").lower().startswith("work")
            else "text.search"
        )
        parsed_search = parse_single_filter(
            search_column, search_string, entity_type
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
                operator="has",
            )
        )

    sort_by = []
    if sort_string:
        sort_by = parse_sort_string(sort_string)

    group_by = []
    if group_by_string:
        group_by = parse_group_by_string(group_by_string)

    select = parse_select_string(select_string) if select_string else []

    # Collapse alias spellings (e.g. `filter=is_oa:true`, `group_by=institution.id`)
    # to one canonical identity at the URL-input boundary (#455). Idempotent; the
    # alias stays accepted on input, it's just normalized for everything downstream.
    # Legacy `?include_xpac=true` ⇒ corpus="all" (#481 leftover, #498). Set before
    # canonicalize: an `is_xpac:` filter present in `filter_rows` redirects to
    # `corpus` there and OVERRIDES this, matching the executor's precedence
    # (explicit filter > include_xpac > core).
    corpus = "all" if include_xpac else "core"
    return canonicalize_oqo_column_ids(OQO(
        get_rows=entity_type,
        corpus=corpus,
        filter_rows=filter_rows,
        sort_by=sort_by,
        sample=sample,
        group_by=group_by,
        select=select,
        seed=seed,
        per_page=per_page,
        page=page,
        cursor=cursor,
    ))


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

    For `.search`-suffix columns the default operator is `has` (free-text
    matching); for all other columns it's `is` (exact equality).
    """
    # Coerce curly/smart double-quotes to ASCII and collapse a run of 2+
    # double-quotes to a single delimiter (`"""universiteit maastricht"""` ->
    # `"universiteit maastricht"`), so the OQO carries a clean canonical value
    # (renders cleanly + the rendered OQL re-parses). Mirrors the OQL lexer's
    # position-preserving collapse. (oxjob #363)
    value = re.sub('"{2,}', '"', value.translate(CURLY_DQUOTE_MAP))
    # Lucene-style boolean inside a .search value (AND/OR/NOT keywords,
    # optionally with parens) lifts to a BranchFilter tree of has-leaves.
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

    # Quoted non-search values: a single enclosing pair of double-quotes means
    # "the spaces inside are literal, not AND operators" — strip it before any
    # further parsing, mirroring the live engine (core/filter.py `is_quoted`).
    # The pipe-OR split below still applies, so `"a|b c|d"` is OR of [a, "b c", d]
    # with the multi-word value kept whole. Search fields keep their quotes
    # (exact-phrase semantics, handled in the .search path above). (#363)
    if (
        len(value) >= 2
        and value.startswith('"')
        and value.endswith('"')
        and "search" not in field
    ):
        value = value[1:-1]

    # Handle OR (pipe) in values
    if "|" in value:
        return parse_or_values(field, value)

    # Within-field NOT (`!`) in a `.search` value: the compact OpenAlex form
    # `term!"phrase"` = term AND NOT (exact) phrase. Live-verified on prod:
    # `title_and_abstract.search:teacher!"academic teacher"` == `teacher`
    # minus exact `"academic teacher"`. The parser used to keep the whole string
    # as one opaque `has` value, so the OQO carried no negation and the
    # renderer dropped the `!` → a NOT silently became an AND (oxjob #431,
    # zd#8101). Decompose into a positive clause + negated clause(s) on the same
    # field; the renderer spells the negation `does not contain`. A LEADING `!`
    # is value-level negation (handled below), not within-field NOT.
    if field.endswith(".search") and _has_within_field_not(value):
        return parse_search_within_field_not(field, value)

    default_op = _default_operator_for(field)

    # Handle null
    if value == "null":
        return LeafFilter(column_id=field, value=None, operator=default_op)

    if value == "!null":
        return LeafFilter(column_id=field, value=None, operator=default_op, is_negated=True)

    # Collection membership ref (col_…), incl. the negated `!col_…` form — BEFORE the
    # generic negation handler so the operator is `in collection`, not `is`. (#363)
    _neg = value.startswith("!")
    _core = value[1:] if _neg else value
    if _COLLECTION_ID_RE.match(_core):
        return LeafFilter(column_id=field, value=_core,
                          operator="in collection", is_negated=_neg)

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
    """`.search`-suffix columns default to `has`; everything else to `is`."""
    return "has" if field.endswith(".search") else "is"


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
        elif field.endswith(".search") and _has_within_field_not(part):
            # An OR member that itself carries within-field NOT (`a|b!c`) becomes
            # an AND of [positive, negated…] within this OR branch (`|` is the
            # outermost operator). (oxjob #431)
            sub = parse_search_within_field_not(field, part)
            filters.append(sub[0] if len(sub) == 1
                           else BranchFilter(join="and", filters=sub))
        else:
            filters.append(LeafFilter(
                column_id=field,
                value=part,
                operator=default_op,
            ))

    return BranchFilter(join="or", filters=filters)


def _split_unquoted(value: str, delim: str) -> List[str]:
    """Split `value` on `delim`, ignoring delimiters inside double-quoted runs
    (so the `!` in `"hello!world"` is literal phrase text, not a separator)."""
    parts: List[str] = []
    current = ""
    in_quotes = False
    for ch in value:
        if ch == '"':
            in_quotes = not in_quotes
            current += ch
        elif ch == delim and not in_quotes:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _has_within_field_not(value: str) -> bool:
    """True iff `value` carries a within-field NOT (`!`): an unquoted `!` that is
    neither the leading character (a leading `!` is value-level negation, handled
    separately) nor a trailing one with no operand after it (`hello!` stays an
    opaque value, unchanged). Requires a non-empty positive run AND at least one
    non-empty negated run."""
    segs = _split_unquoted(value, "!")
    if len(segs) < 2 or segs[0].strip() == "":
        return False
    return any(seg.strip() != "" for seg in segs[1:])


def _search_not_leaf(field: str, operand: str, is_negated: bool) -> LeafFilter:
    """Build one `.search` leaf for a within-field-NOT operand. A quoted operand
    is an exact phrase → route to the `.search.exact` column (matching the live
    API, where the subtracted set size equals the exact-phrase count); a bare
    operand stays on the stemmed `.search` column. Operator is always `has`
    (note `.search.exact` does not end in `.search`, so the default-operator
    helper would wrongly pick `is` — set it explicitly)."""
    operand = operand.strip()
    if len(operand) >= 2 and operand.startswith('"') and operand.endswith('"'):
        return LeafFilter(column_id=field + ".exact", value=operand,
                          operator="has", is_negated=is_negated)
    return LeafFilter(column_id=field, value=operand,
                      operator="has", is_negated=is_negated)


def parse_search_within_field_not(field: str, value: str) -> List[LeafFilter]:
    """Decompose a `.search` value's within-field NOT (`!`) into clauses.

    `teacher!"academic teacher"` → [has teacher,
    does-not-have exact "academic teacher"]. The leading run is the positive
    term/run; each subsequent `!run` is a negated clause on the SAME field
    (multiple `!`s chain: `a!b!c` = a AND NOT b AND NOT c). Quoted run → exact
    (`.search.exact`), bare run → stemmed (`.search`). Mirrors how the parser
    already splits `|` into OR branches; the renderer + grammar need no change —
    OQL already expresses this via `does not contain`. (oxjob #431, zd#8101.)
    """
    segs = _split_unquoted(value, "!")
    leaves: List[LeafFilter] = []
    for idx, seg in enumerate(segs):
        if seg.strip() == "":
            continue
        leaves.append(_search_not_leaf(field, seg, is_negated=idx > 0))
    return leaves


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
# the phrase (so `supply chain` inside `(supply chain)` is one has leaf,
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

    All leaves are `LeafFilter(column_id=field, operator="has")`.
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
            return LeafFilter(column_id=field, value="", operator="has")
        kind, text = tok
        if kind == "LPAREN":
            consume()
            inner = parse_expr()
            if peek() and peek()[0] == "RPAREN":
                consume()
            return inner
        if kind == "PHRASE":
            consume()
            # Keep the surrounding double-quotes on the leaf value: a `.search`
            # phrase value carries its quotes as the IR convention (the same shape
            # the standalone `parse_single_filter` path produces — it does NOT strip
            # quotes for search fields). Stripping them here made a multi-word phrase
            # inside an OR/AND group render BARE (`(reduced order model or surrogate
            # model)`), which is invalid, un-reparseable OQL (a space is an implicit
            # AND, so it mixes AND/OR at one level). The renderer relies on the quotes
            # to print the value as a phrase. (oxjob #363 case 8a)
            return LeafFilter(column_id=field, value=text, operator="has")
        # Unexpected token (shouldn't happen for well-formed input)
        consume()
        return LeafFilter(column_id=field, value=text, operator="has")

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

    A metric-aggregate group sort (oxjob #389) uses the dotted pseudo-field form
    `<column>.<metric>` (metric ∈ mean/sum/min/max), e.g. `cited_by_count.mean:desc`.
    It parses to `SortBy(column_id="cited_by_count", aggregate="mean", ...)`. Only
    the trailing `.<metric>` is peeled off, so dotted column names with a non-metric
    last segment (e.g. `primary_topic.id`) are left intact as ordinary sort columns.
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
        column, aggregate = _split_metric_sort_column(column)
        sort_by.append(
            SortBy(column_id=column, direction=direction, aggregate=aggregate)
        )
    return sort_by


# Public metric names valid in the dotted `<column>.<metric>` group-sort form
# (oxjob #389). Mirrors core.group_by.buckets.GROUP_BY_METRICS keys; kept local so
# the pure URL parser stays free of the elasticsearch-importing buckets module.
_METRIC_SORT_AGGREGATES = ("mean", "sum", "min", "max")


def _split_metric_sort_column(column):
    """Peel a trailing `.<metric>` off a sort column, returning
    `(column_id, aggregate)`. `(column, None)` when there is no metric suffix.
    Only the LAST dotted segment is considered the metric, so a column like
    `apc_paid.value_usd` (no metric tail) is returned unchanged."""
    field_part, _, last = column.rpartition(".")
    if field_part and last in _METRIC_SORT_AGGREGATES:
        return field_part, last
    return column, None
