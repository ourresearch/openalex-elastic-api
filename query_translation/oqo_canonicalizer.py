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
   NOT lives only on leaves after NNF), giving order-independent output — but ONLY when
   `sort_operands=True` (the default). The OQL-text / builder render paths pass
   `sort_operands=False` to PRESERVE the user's given order (charter decision 30, #363);
   only the legacy-URL and NL→OQO paths (machine-shaped, unordered input) keep the sort.

Values are *bare* (the namespace is the column_id, resolved via the column
registry) — there is no entity-id prefix normalization. See docs/oql-spec.md.
"""

import json
from dataclasses import replace
from typing import List, Union, Any
from query_translation.oqo import (OQO, LeafFilter, BranchFilter, FilterType, SortBy, GroupBy,
                                   MeasureFilter, AffiliationFilter, canonicalize_oqo_column_ids)
from query_translation.oql_lang import (
    canon_value_for_column,
    canonical_exact_search_value,
    _is_search_leaf,
    is_numeric_column,
    split_exact_words,
)


def canonicalize_oqo(oqo: OQO, sort_operands: bool = True) -> OQO:
    """
    Canonicalize an OQO object into deterministic canonical form.

    Args:
        oqo: The OQO object to canonicalize
        sort_operands: when True (default), commutative operands are alphabetically
            sorted — top-level `filter_rows` and the children of every AND/OR group —
            for an order-independent canonical form (cache keys, hashing, dedup, and
            the legacy-URL / NL→OQO paths, where input order is machine-shaped and not
            meaningful). When False, the user's given operand order is **preserved**
            end-to-end (charter decision 30, #363): OQL-text and builder/direct-OQO
            input render in the order the user wrote, so the LEGO builder doesn't jump
            a new clause to its alphabetical slot and SR authors keep their block order.
            All the OTHER canonical transforms (NNF, type coercion, column-id collapse,
            flatten/hoist, redundant-sort drop) run regardless. NOTE: with
            sort_operands=False, OQO is no longer a single canonical form on the OQL
            side — `where A and B` and `where B and A` become distinct; idempotence
            (render→parse→render fixed point) still holds.

    Returns:
        A new canonicalized OQO object
    """
    # Collapse alias column_id spellings to one canonical identity FIRST (#455), so
    # two spellings of the same property (`is_oa` vs `open_access.is_oa`) produce one
    # cache/hash key, and the value-typing below keys off the canonical column. The
    # OQO-construction seams already canonicalize, so for parsed/url OQOs this is a
    # no-op; it's the safety net for OQOs built another way before hashing.
    oqo = canonicalize_oqo_column_ids(oqo)
    canonical_filters = []
    for f in oqo.filter_rows:
        nnf_f = push_negation(f, negate=False)  # NNF first
        canonical_f = canonicalize_filter(nnf_f, sort_operands)
        if canonical_f is not None:
            # Flatten if we get a single-child result that should be unwrapped
            if isinstance(canonical_f, list):
                canonical_filters.extend(canonical_f)
            # filter_rows is itself an implicit AND, so a top-level AND branch is
            # hoisted into separate rows. This keeps the two ways of spelling the
            # same thing convergent: `x is not (a or b)` (parsed as a negated OR,
            # De Morgan'd to an AND branch here) and `x is (not a and not b)`
            # (parsed as a top-level AND that parse() already flattens) both
            # canonicalize to the same multi-row form.
            elif isinstance(canonical_f, BranchFilter) and canonical_f.join == "and" \
                    and not canonical_f.is_negated:
                canonical_filters.extend(canonical_f.filters)
            else:
                canonical_filters.append(canonical_f)

    # NOTE: strict integer bound pairs are NOT collapsed to an inclusive range
    # (`> 42 AND < 100` stays strict, no `>= 43 AND <= 99` inference) — the dash
    # range literal it fed was removed (charter decision 24). Strict inequalities
    # now stay exactly as written; more faithful, no inference.

    # Top-level filter_rows are an implicit AND -> commutative -> sort for stability,
    # UNLESS we're preserving the user's given order (decision 30, #363).
    if sort_operands:
        canonical_filters.sort(key=_sort_key)

    canonical_sort_by = _drop_redundant_default_sort(canonical_filters, oqo.sort_by)

    return OQO(
        get_rows=oqo.get_rows.lower(),  # Normalize entity type to lowercase
        # Corpus selection passes through unchanged (#481); "core" is the default,
        # left as-is so canonical OQOs stay minimal/comparable.
        corpus=oqo.corpus,
        filter_rows=canonical_filters,
        # sort_by order is meaningful (tiebreaker priority: primary, secondary,
        # …) -> preserved, NOT sorted (unlike the commutative filter_rows above).
        sort_by=canonical_sort_by,
        sample=oqo.sample,
        # group_by order is meaningful (dim order) -> preserved; the trees inside a
        # split (conditions, listed searches, the group filter) canonicalize like
        # filter_rows, but their LIST order is the group order -> preserved.
        group_by=[_canonicalize_split(g, sort_operands) for g in oqo.group_by],
        calculate=list(oqo.calculate),
        # walks (oxjob #1535): their order is the query's order; a walk's `where`
        # canonicalizes like filter_rows
        walks=[replace(w, where=_canonicalize_tree(w.where, sort_operands))
               if w.where is not None else w for w in oqo.walks],
        each=oqo.each,
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


def _any_search_leaf(filters: List[FilterType]) -> bool:
    """True if any leaf anywhere under `filters` is a search (`.search`) leaf —
    the condition under which the engine treats the query as a search query and
    defaults its sort to relevance. Mirrors `core.search.check_is_search_query`
    (whose search keys all contain `.search`)."""
    for f in filters:
        if isinstance(f, LeafFilter):
            if _is_search_leaf(f):
                return True
        elif isinstance(f, BranchFilter) and _any_search_leaf(f.filters):
            return True
    return False


def _drop_redundant_default_sort(filter_rows: List[FilterType], sort_by) -> List[SortBy]:
    """Drop an explicit sort that merely restates the query's implicit default.

    A search-bearing works query already defaults to `relevance_score desc`
    (`core/shared_view.apply_sorting`; relevance is only even *valid* with a
    search clause), so a lone `sort by relevance_score desc` is redundant noise —
    omit it from the canonical form so the OQL render reads cleanly and a
    relevance-sorted search round-trips to the no-sort canonical OQO. Any extra
    tiebreaker keys, a non-relevance primary, `asc`, or a non-search query keep
    the sort verbatim. (oxjob #363)
    """
    if (len(sort_by) == 1
            and sort_by[0].column_id == "relevance_score"
            and sort_by[0].direction == "desc"
            and _any_search_leaf(filter_rows)):
        return []
    return [SortBy(s.column_id, s.direction) for s in sort_by]


def _canonicalize_tree(f, sort_operands: bool = True):
    """One filter tree (a condition, a listed search, a group filter) in canonical
    form: NNF, then the leaf/branch transforms; a flattened list becomes an AND."""
    c = canonicalize_filter(push_negation(f, negate=False), sort_operands)
    if isinstance(c, list):
        if sort_operands:
            c.sort(key=_sort_key)
        return c[0] if len(c) == 1 else BranchFilter(join="and", filters=c)
    return c


def _canonicalize_split(g: GroupBy, sort_operands: bool = True) -> GroupBy:
    """A split (oxjob #1530): trees inside it canonicalize, list order stays."""
    if g.is_plain:
        return g
    values = g.values
    if values is not None:
        values = [_canonicalize_tree(v, sort_operands)
                  if isinstance(v, (LeafFilter, BranchFilter))
                  else canonicalize_value(v, g.column_id) for v in values]
    conditions = g.conditions
    if conditions is not None:
        conditions = [_canonicalize_tree(c, sort_operands) for c in conditions]
    where = _canonicalize_tree(g.where, sort_operands) if g.where is not None else None
    return GroupBy(column_id=g.column_id, values=values, bins=g.bins,
                   conditions=conditions, where=where)


# NOT of a comparison is the opposite comparison (group filters on measures).
_NEGATED_COMPARISON = {">": "<=", ">=": "<", "<": ">=", "<=": ">"}


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
    if isinstance(f, AffiliationFilter):
        return replace(f, is_negated=bool(f.is_negated) ^ bool(negate))
    if isinstance(f, MeasureFilter):
        eff = bool(f.is_negated) ^ bool(negate)
        if eff and f.operator in _NEGATED_COMPARISON:
            return MeasureFilter(measure=f.measure, column_id=f.column_id,
                                 operator=_NEGATED_COMPARISON[f.operator], value=f.value)
        return MeasureFilter(measure=f.measure, column_id=f.column_id,
                             operator=f.operator, value=f.value, is_negated=eff)
    return f


# Order the four comparison bounds within a column lower-before-upper so a range
# renders `year >= 2019 and year <= 2023` (decision 24). The column_id is the first
# JSON key and all non-comparison operator values start with a letter, so remapping
# only ever reorders same-column bound pairs — every other ordering is byte-identical
# to the plain sorted-keys JSON.
_BOUND_ORDER = {">": "0", ">=": "1", "<": "2", "<=": "3"}


def _sort_key(f: FilterType) -> str:
    """Total order over filters for canonical operand sorting: the JSON of the
    filter's dict with sorted keys, with comparison bounds remapped so a column's
    lower bound sorts before its upper bound. Stable and deterministic."""
    d = f.to_dict()
    if isinstance(f, LeafFilter) and f.operator in _BOUND_ORDER:
        d = {**d, "operator": _BOUND_ORDER[f.operator]}
    if isinstance(f, MeasureFilter):
        # group filters read calculations first (`count of those works > (10) and
        # h-index > (20)`): "0" sorts before every JSON object's "{"
        return "0" + json.dumps(d, sort_keys=True, ensure_ascii=True)
    return json.dumps(d, sort_keys=True, ensure_ascii=True)


def canonicalize_filter(f: FilterType, sort_operands: bool = True) -> Union[FilterType, List[FilterType], None]:
    """
    Canonicalize a single filter.

    `sort_operands` is threaded to branch children (see `canonicalize_oqo`).

    Returns:
        - A canonicalized filter
        - A list of filters (if a group was flattened)
        - None (if filter should be removed)
    """
    if isinstance(f, LeafFilter):
        return canonicalize_leaf_filter(f, sort_operands)
    elif isinstance(f, BranchFilter):
        return canonicalize_branch_filter(f, sort_operands)
    elif isinstance(f, (MeasureFilter, AffiliationFilter)):
        return f
    return None


# whole-day date column -> its inclusive lower-bound column (the date has no time of day)
_NEXT_DAY_BOUND = {"publication_date": "from_publication_date", "created_date": "from_created_date"}


def canonicalize_leaf_filter(f: LeafFilter, sort_operands: bool = True) -> Union[LeafFilter, BranchFilter]:
    """
    Canonicalize a leaf filter.

    - Normalizes value types (string "true" -> bool True; numeric strings -> int)
    - Preserves the `is_negated` polarity bit (already pushed to leaves by NNF)
    - Values stay *bare* (no entity-id prefix normalization)
    - A `.search.exact` value normalizes to the engine's canonical spelling
      (singleton quotes stripped), and a bare multi-word clean run — the
      no-stem AND-of-words — splits into per-token leaves (#633): AND-branch
      when positive, De Morgan OR-branch of negated leaves when negated
      (NOT(a AND b) = (NOT a) OR (NOT b)). The parse doors already build this
      shape; doing it here too makes direct-OQO submissions converge on the
      same canonical form, so the OQL render never sees the one-leaf shape it
      can't render faithfully (its `not` bound only the first token).
    """
    if isinstance(f.value, OQO):
        # a set defined by a whole query (oxjob #1535): canonical inside too
        return LeafFilter(column_id=f.column_id, value=canonicalize_oqo(f.value, sort_operands),
                          operator="in", is_negated=bool(f.is_negated))
    value = canonicalize_value(f.value, f.column_id)
    operator = f.operator or "is"

    # A strict lower bound on a whole-day date is the next day, inclusive (oxjob #1555,
    # Jason 2026-10-09): `date > 2021-06-01` is `from_publication_date 2021-06-02`, so
    # the echo reads `published since 2021-06-02` and never the ambiguous "after".
    col = _NEXT_DAY_BOUND.get(f.column_id)
    if col is not None and operator == ">" and isinstance(value, str):
        from query_translation.oql_lang import next_day
        day = next_day(value)
        if day is not None:
            return LeafFilter(column_id=col, value=day, operator="is", is_negated=bool(f.is_negated))

    if f.column_id.endswith(".search.exact") and isinstance(value, str):
        value = canonical_exact_search_value(value)
        words = split_exact_words(value)
        if words:
            leaves = [
                LeafFilter(column_id=f.column_id, value=w, operator=operator,
                           is_negated=bool(f.is_negated))
                for w in words
            ]
            if sort_operands:
                leaves.sort(key=_sort_key)
            return BranchFilter(join="or" if f.is_negated else "and",
                                filters=leaves)

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
    through untouched. Type coercion is keyed off the engine's column kinds
    (`is_numeric_column`), so it can't drift from the field registry.
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

    # Integer normalization for numeric columns
    if isinstance(value, str) and is_numeric_column(column_id):
        try:
            # Check if it's an integer
            if "." not in value:
                return int(value)
            else:
                return float(value)
        except ValueError:
            pass

    # Enum value-casing (country codes -> upper, enum slugs -> lower). The OQL
    # parser already canonicalizes case on its way in; an OQO-JSON submit bypasses
    # the parser, so apply the same column-casing here for round-trip stability and
    # to avoid case-sensitive ES misses (e.g. country=ca vs the indexed CA).
    if isinstance(value, str):
        value = _vocab_code_for_name(value, column_id)
        return _short_entity_id(canon_value_for_column(value, column_id), column_id)

    return value


_CONTINENT_CODES = {"af": "Q15", "an": "Q51", "as": "Q48", "eu": "Q46", "na": "Q49",
                    "oc": "Q55643", "sa": "Q18"}


def _vocab_code_for_name(value: str, column_id: str) -> str:
    """A closed vocabulary's name stands for its code (oxjob #1555, Haiku's cow path):
    `continent is (Africa)`, `country is ("United Kingdom")`, `language is (English)`.
    Only when the value isn't already a code and exactly one entry has that name."""
    from query_translation import oql_lang as L
    from query_translation.oql_renderer import _config_table, is_vocab_member
    from query_translation.validator import CLOSED_VOCAB_NAMESPACE
    ns = CLOSED_VOCAB_NAMESPACE.get(L.entity_type_for_column(column_id) or "")
    if ns is None or is_vocab_member(ns, value):
        return value
    if ns == "continents" and value.strip().lower() in _CONTINENT_CODES:
        # the two-letter continent codes people reach for: `[Africa](AF)` (map cow path,
        # 2026-10-09); our IDs are Wikidata's
        return _CONTINENT_CODES[value.strip().lower()]
    table = _config_table(ns) or {}
    codes = [code for code, name in table.items() if name.lower() == value.strip().lower()]
    return codes[0] if len(codes) == 1 else value


def _short_entity_id(value: str, column_id: str) -> str:
    """An entity column's ID in its short form (oxjob #1555): `https://openalex.org/
    I63966007`, `i63966007`, `types/article` -> `I63966007`, `article`, the same as the
    OQL parser writes them, so a URL-built OQO and its OQL echo agree. Only values of
    the column's ID shape change (a DOI's `/` is safe: DOI columns aren't entities)."""
    from query_translation import oql_lang as L
    fld = L._BY_COLUMN.get(column_id)
    if (column_id in L._SELF_ID_COLUMNS or value.startswith("col_")
            or (fld is not None and fld.kind not in ("id", "enum"))):
        return value
    ns = L.entity_type_for_column(column_id)
    return L._short_id(ns, value) if ns is not None else value


def canonicalize_branch_filter(f: BranchFilter, sort_operands: bool = True) -> Union[FilterType, List[FilterType], None]:
    """
    Canonicalize a branch filter.

    Rules:
    1. Recursively canonicalize children
    2. Remove empty children
    3. Flatten nested same-join groups (AND inside AND)
    4. Unwrap single-child groups
    5. **Sort** children (AND/OR are commutative; NOT lives only on leaves after NNF)
       — unless `sort_operands` is False, in which case the user's value order is
       preserved (decision 30, #363).

    Assumes the branch is already in NNF (branch-level negation pushed to leaves
    by `push_negation`), so `is_negated` on a BranchFilter is not expected here.
    """
    canonical_children: List[FilterType] = []

    for child in f.filters:
        canonical_child = canonicalize_filter(child, sort_operands)
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

    # Sort operands for order-independent canonical output, unless preserving the
    # user's given value order (decision 30, #363).
    if sort_operands:
        canonical_children.sort(key=_sort_key)

    return BranchFilter(
        join=f.join,
        filters=canonical_children,
    )

