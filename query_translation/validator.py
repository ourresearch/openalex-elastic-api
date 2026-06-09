"""Validator — checks an OQO against the live entity-property catalog.

Source of truth is `core.properties.ENTITY_PROPERTIES` (#331; formerly the #294
column registry): the per-entity catalog built at boot from the same `Field`
objects the filter layer executes. Validation answers, for each leaf filter,
three questions:

  (a) is `column_id` a real property on the OQO's `get_rows` entity? -> invalid_column
  (b) does `operator` fit that property's type?                     -> invalid_operator_for_column
  (c) does `value` match the property's type?                       -> invalid_value_type

Strict: every one of these is a hard error (the route returns 400). This catches
nonsense like `cited_by_count contains 5` or `is_oa is 5` before it reaches ES.

Negation is the `is_negated` polarity bit, not an operator; the OQO->ES translator
applies it uniformly via `~q`, so it is NOT constrained here.
"""

import difflib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.entities import entity_for_id_prefix, get_entity_type
from core.fields import Property
from core.properties import (
    ENTITY_PROPERTIES,
    get_entity_properties,
    get_selectable_fields,
)
from query_translation.oql_renderer import is_vocab_member, vocab_name_to_code
from query_translation.oqo import (
    OQO,
    LeafFilter,
    BranchFilter,
    FilterType,
    SortBy,
    VALID_OPERATORS,
)


@dataclass
class ValidationError:
    """A validation error."""
    type: str
    message: str
    location: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of OQO validation."""
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [
                {"type": e.type, "message": e.message, "location": e.location}
                for e in self.errors
            ],
            "warnings": [
                {"type": w.type, "message": w.message, "location": w.location}
                for w in self.warnings
            ],
        }


# OQO get_rows values that name the same property-catalog entity under a different label.
ENTITY_ALIASES = {"types": "work-types"}

# Closed enumerated value vocabularies: a property whose `entity_type` is one of
# these resolves to a finite code set we can enumerate offline, so a value that
# isn't a literal member is a hard `invalid_value` error (charter: OQL is readable
# but strict — name->code / fuzzy matching is the NL parser's job, not raw OQL).
# The membership set is the renderer's `config/<vocab>.yaml` table (single source
# of truth — validation and name-rendering share it). Maps the Property
# `entity_type` to the renderer's config namespace: identity except work-types,
# whose config namespace is the legacy "types". (oxjob #363; scoped 2026-06-07.)
# Open ID entities (authors/works/institutions/…) are NOT here — millions of
# members, so they're validated by ID-shape/prefix instead (Tier 2, below, keyed
# off the entity registry's `idRegex`). license / source-type / institution-type
# deferred per the scoping note.
CLOSED_VOCAB_NAMESPACE = {
    "countries": "countries",
    "continents": "continents",
    "languages": "languages",
    "sdgs": "sdgs",
    "work-types": "types",
    "oa-statuses": "oa-statuses",
    # Tier-1.5: the topic-hierarchy code vocabs — small, fully-enumerable closed
    # sets (domains 4, fields 26, subfields 252; complete in `config/*.yaml` and
    # matching the live API). Identity-mapped (namespace == entity_type ==
    # renderer config namespace). Protects any column carrying these entity_types
    # (e.g. `primary_topic.field.id`, `topics.domain.id`). (oxjob #363, 2026-06-08.)
    "domains": "domains",
    "fields": "fields",
    "subfields": "subfields",
}

VALID_SORT_ORDERS = {"asc", "desc"}

# Comparison operators (produce range-form ES queries in the translator).
COMPARISON_OPERATORS = {">", ">=", "<", "<="}


def _resolve_property_entity(get_rows: str) -> Optional[str]:
    """Resolve an OQO `get_rows` to its property-catalog key, or None if unknown."""
    if get_rows in ENTITY_PROPERTIES:
        return get_rows
    alias = ENTITY_ALIASES.get(get_rows)
    if alias in ENTITY_PROPERTIES:
        return alias
    return None


def _is_numeric(value: Any) -> bool:
    """True for ints/floats and numeric strings (bools excluded — bool is an int)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


# Loosely: a 4-digit year, optionally -MM, -MM-DD, optionally a T-time suffix.
_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?([T ].*)?$")


def _value_matches_type(field_type: Optional[str], value: Any) -> bool:
    """Check a bare scalar against a column's declared field_type.

    Deliberately lenient on the string-ish types (string/openalex_id/external_id/
    search/phrase) — over-tight ID-shape checks would false-reject valid queries.
    `value is None` (null) is handled by the operator check, not here.
    """
    if value is None:
        return True
    if field_type == "boolean":
        if isinstance(value, bool):
            return True
        return isinstance(value, str) and value.strip().lower() in ("true", "false")
    if field_type == "number":
        return _is_numeric(value)
    if field_type in ("date", "datetime"):
        if isinstance(value, int) and not isinstance(value, bool):
            return 1000 <= value <= 9999  # bare year
        return isinstance(value, str) and bool(_DATE_RE.match(value.strip()))
    # string-ish: openalex_id, external_id, string, search, phrase, collection.
    # Accept any scalar that stringifies cleanly; reject only bools.
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _operator_fits_column(operator: str, value: Any, operators: List[str]) -> bool:
    """Check an OQO operator against a property's supported operator buckets."""
    if value is None:
        # null/!null: only the default operator, and the column must support null.
        return operator == "is" and "null" in operators
    if operator == "is":
        return "eq" in operators
    if operator == "contains":
        return "search" in operators or "phrase" in operators
    if operator in COMPARISON_OPERATORS:
        return "range" in operators or "date_range" in operators
    if operator == "in collection":
        # col_… membership: valid on the dedicated same-type `collection` column,
        # and on any equality-capable entity column (cross-type — the Collection
        # resolves to a set of that column's values). (oxjob #363)
        return "collection" in operators or "eq" in operators
    # Unknown operator string — surfaced separately as invalid_operator.
    return False


# `relevance_score` is a synthetic sort key, not a filterable column: legacy
# `core/sort.py` maps it to ES `_score`. It is sortable but never appears in the
# filter-column property catalog, so it gets its own allow-rule in the sort check below
# (gated on a search clause being present, descending only — see legacy
# `core/shared_view.py:apply_sorting`).
RELEVANCE_SORT_COLUMN = "relevance_score"

# `count` and `key` are synthetic sort keys valid ONLY when a group_by is present:
# they order the returned buckets by doc count or bucket key, not the entity's rows.
# Legacy `core/sort.py:get_sort_fields` special-cases them for group_by; they are
# not entity columns, so they get their own allow-rule below, gated on group_by
# (#323 Pattern G1 — without it `?group_by=type&sort=count:desc` 400s `invalid_column`).
GROUP_BY_SORT_KEYS = {"count", "key"}

# Metric-aggregate group sort (oxjob #389): a `SortBy` may carry an `aggregate`
# (mean/sum/min/max) to order the group_by buckets by a metric sub-aggregation of
# its (numeric) `column_id`, e.g. funders ranked by mean(cited_by_count). Mirrors
# core.group_by.buckets.GROUP_BY_METRICS keys; kept local so the validator doesn't
# import the elasticsearch-heavy buckets module.
VALID_SORT_AGGREGATES = {"mean", "sum", "min", "max"}


def _has_search_clause(filter_rows: List["FilterType"]) -> bool:
    """True if any leaf in the filter tree is a `*.search` (free-text) clause.

    Mirrors legacy `core.search.check_is_search_query`: a search query is present
    when a `?search=` (now mapped to a `default.search` filter row, #323 2a) or
    any `*.search` / `*.search.exact` filter is present. In canonical OQO form
    `.search.exact` is rewritten to `.search`, so `endswith(".search")` over all
    leaves catches every legacy search key (default/title/abstract/fulltext/
    semantic/keyword/display_name/title_and_abstract/raw_*).
    """
    for f in filter_rows:
        if isinstance(f, BranchFilter):
            if _has_search_clause(f.filters):
                return True
        elif isinstance(f, LeafFilter):
            if isinstance(f.column_id, str) and f.column_id.endswith(".search"):
                return True
    return False


_SUGGEST_CUTOFF = 0.8  # min edit-distance ratio; below this, suggest nothing
                       # (a spurious suggestion is worse than none — oxjob #423).


def _suggest_columns(
    bad_id: Any, column_ids: List[str], max_suggestions: int = 2
) -> List[str]:
    """Closest registered column id(s) to a missed `bad_id`, for an
    `invalid_column` "did you mean" hint (oxjob #423). Pure; offline-testable.

    Two tiers, segment-aware first so the common translator/typo footguns are
    legible:
      Tier 1 — same dot-segments in a different order (e.g.
        `<f>.exact.search` -> `<f>.search.exact`). A pure permutation: instantly
        reveals "wrong order / shape", not "field doesn't exist".
      Tier 2 — plain edit-distance near-misses (typos: `pubilcation_year` ->
        `publication_year`) at ratio >= _SUGGEST_CUTOFF.
    Tier-1 hits rank ahead of tier-2; results are deduped and capped. Returns []
    when nothing is close (e.g. a clearly-bogus `zzzzz`)."""
    if not isinstance(bad_id, str) or not bad_id:
        return []
    bad_segs = bad_id.split(".")
    ranked: List[str] = []

    # Tier 1: permutations of the same segment multiset (different order).
    if len(bad_segs) > 1:
        permutations = [
            c for c in column_ids
            if c != bad_id and sorted(c.split(".")) == sorted(bad_segs)
        ]
        permutations.sort(
            key=lambda c: difflib.SequenceMatcher(None, bad_id, c).ratio(),
            reverse=True,
        )
        ranked.extend(permutations)

    # Tier 2: edit-distance near-misses.
    for c in difflib.get_close_matches(
        bad_id, column_ids, n=max_suggestions, cutoff=_SUGGEST_CUTOFF
    ):
        if c not in ranked:
            ranked.append(c)

    return ranked[:max_suggestions]


class OQOValidator:
    """Validates OQO objects against the live entity-property catalog."""

    def validate(self, oqo: OQO) -> ValidationResult:
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        entity = _resolve_property_entity(oqo.get_rows)
        if entity is None:
            errors.append(ValidationError(
                type="invalid_entity",
                message=f"'{oqo.get_rows}' is not a valid entity type",
                location="get_rows",
            ))
            # Without a known entity we can't resolve columns; stop here.
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        columns = get_entity_properties(entity)

        for i, f in enumerate(oqo.filter_rows):
            errors.extend(self._validate_filter(f, columns, f"filter_rows[{i}]"))

        # `sort_by` is an ordered list of sort keys (multi-column sort, #333).
        # Each key is validated on its own merits — exactly the single-sort rules
        # applied per element. Locations are indexed (`sort_by[i].…`) so a caller
        # can point at the offending key in a multi-column sort.
        has_search = _has_search_clause(oqo.filter_rows)
        for i, key in enumerate(oqo.sort_by):
            errors.extend(self._validate_sort_key(
                key, i, columns, has_search, bool(oqo.group_by), oqo.get_rows,
            ))

        if oqo.sample is not None:
            if not isinstance(oqo.sample, int) or isinstance(oqo.sample, bool) \
                    or oqo.sample < 1:
                errors.append(ValidationError(
                    type="invalid_sample",
                    message="Sample must be a positive integer",
                    location="sample",
                ))

        # group_by dimensions must be non-empty strings AND real columns.
        for i, g in enumerate(oqo.group_by):
            column_id = getattr(g, "column_id", None)
            if not column_id or not isinstance(column_id, str):
                errors.append(ValidationError(
                    type="invalid_group_by",
                    message="group_by dimension must have a non-empty string column_id",
                    location=f"group_by[{i}].column_id",
                ))
            elif column_id not in columns:
                errors.append(ValidationError(
                    type="invalid_column",
                    message=(
                        f"'{column_id}' is not a groupable column on "
                        f"'{oqo.get_rows}'"
                    ),
                    location=f"group_by[{i}].column_id",
                ))

        # --- logistics layer (#318) ------------------------------------------

        # select: each entry must be a selectable result-field on the entity.
        # Selectable fields are the entity's result-schema fields (NOT the filter
        # property catalog above) — see core.properties.get_selectable_fields.
        if oqo.select:
            selectable = get_selectable_fields(entity)
            for i, col in enumerate(oqo.select):
                if not isinstance(col, str) or not col:
                    errors.append(ValidationError(
                        type="invalid_select_column",
                        message="select column must be a non-empty string",
                        location=f"select[{i}]",
                    ))
                elif selectable is not None and col not in selectable:
                    errors.append(ValidationError(
                        type="invalid_select_column",
                        message=(
                            f"'{col}' is not a selectable field on "
                            f"'{oqo.get_rows}'"
                        ),
                        location=f"select[{i}]",
                    ))

        # pagination: page and cursor are mutually exclusive.
        if oqo.page is not None and oqo.cursor is not None:
            errors.append(ValidationError(
                type="invalid_pagination",
                message="'page' and 'cursor' are mutually exclusive",
                location="cursor",
            ))

        # per_page must be an integer in 1..200.
        if oqo.per_page is not None:
            if not isinstance(oqo.per_page, int) or isinstance(oqo.per_page, bool) \
                    or oqo.per_page < 1 or oqo.per_page > 200:
                errors.append(ValidationError(
                    type="invalid_per_page",
                    message="per_page must be an integer between 1 and 200",
                    location="per_page",
                ))

        # page must be an integer >= 1.
        if oqo.page is not None:
            if not isinstance(oqo.page, int) or isinstance(oqo.page, bool) \
                    or oqo.page < 1:
                errors.append(ValidationError(
                    type="invalid_page",
                    message="page must be an integer >= 1",
                    location="page",
                ))

        # seed without sample is harmless but inert — non-blocking warning.
        if oqo.seed is not None and oqo.sample is None:
            warnings.append(ValidationError(
                type="seed_without_sample",
                message="'seed' has no effect without 'sample'",
                location="seed",
            ))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_sort_key(
        self,
        key: SortBy,
        index: int,
        columns: Dict[str, Property],
        has_search: bool,
        has_group_by: bool,
        get_rows: str,
    ) -> List[ValidationError]:
        """Validate one sort key in the ordered `sort_by` list.

        These are the single-sort rules applied per element. `column_id` must be
        a real column on the entity, OR a synthetic sort key:
          - `relevance_score` — sortable but not filterable (legacy core/sort.py
            -> ES `_score`); gated on a search clause and descending-only (legacy
            apply_sorting rejects ascending relevance and relevance with no search).
          - `count` / `key` — bucket-ordering keys, valid only when a group_by is
            present (legacy core/sort.py:get_sort_fields special-cases them).
        And the direction must be `asc`/`desc`.
        """
        errors: List[ValidationError] = []
        loc = f"sort_by[{index}]"

        if key.column_id == RELEVANCE_SORT_COLUMN:
            if not has_search:
                errors.append(ValidationError(
                    type="relevance_sort_requires_search",
                    message=(
                        "Sorting by 'relevance_score' requires a search clause "
                        "(e.g. ?search=example or a *.search filter such as "
                        "display_name.search:example)."
                    ),
                    location=f"{loc}.column_id",
                ))
            if key.direction == "asc":
                errors.append(ValidationError(
                    type="invalid_sort_order",
                    message="Sorting by 'relevance_score' ascending is not allowed.",
                    location=f"{loc}.direction",
                ))
        elif key.aggregate is not None:
            # Metric-aggregate group sort (oxjob #389): order the group_by buckets
            # by a metric sub-aggregation (mean/sum/min/max) of a numeric column.
            # Valid only when (a) a group_by is present, (b) the aggregate name is
            # known, and (c) `column_id` is a real NUMERIC column on the entity.
            if not has_group_by:
                errors.append(ValidationError(
                    type="aggregate_sort_requires_group_by",
                    message=(
                        "A metric-aggregate sort "
                        f"('{key.column_id}.{key.aggregate}') is only valid with a "
                        "group_by."
                    ),
                    location=f"{loc}.aggregate",
                ))
            if key.aggregate not in VALID_SORT_AGGREGATES:
                errors.append(ValidationError(
                    type="invalid_sort_aggregate",
                    message=(
                        f"'{key.aggregate}' is not a valid sort aggregate. "
                        f"Use one of: {', '.join(sorted(VALID_SORT_AGGREGATES))}."
                    ),
                    location=f"{loc}.aggregate",
                ))
            entry = columns.get(key.column_id)
            if entry is None:
                errors.append(ValidationError(
                    type="invalid_column",
                    message=(
                        f"'{key.column_id}' is not a column on '{get_rows}'"
                    ),
                    location=f"{loc}.column_id",
                ))
            elif entry.type != "number":
                errors.append(ValidationError(
                    type="invalid_sort_aggregate_column",
                    message=(
                        f"Cannot compute a metric aggregate over non-numeric "
                        f"column '{key.column_id}' (type '{entry.type}'). "
                        f"Metric-aggregate sort requires a numeric column."
                    ),
                    location=f"{loc}.column_id",
                ))
        elif has_group_by and key.column_id in GROUP_BY_SORT_KEYS:
            # Bucket-ordering sort key (count/key) — valid because group_by is set.
            pass
        elif key.column_id and key.column_id not in columns:
            errors.append(ValidationError(
                type="invalid_column",
                message=(
                    f"'{key.column_id}' is not a sortable column on "
                    f"'{get_rows}'"
                ),
                location=f"{loc}.column_id",
            ))

        if key.direction and key.direction not in VALID_SORT_ORDERS:
            errors.append(ValidationError(
                type="invalid_sort_order",
                message=(
                    f"'{key.direction}' is not a valid sort order. "
                    f"Use 'asc' or 'desc'."
                ),
                location=f"{loc}.direction",
            ))

        return errors

    def _validate_filter(
        self, f: FilterType, columns: Dict[str, Property], location: str
    ) -> List[ValidationError]:
        if isinstance(f, LeafFilter):
            return self._validate_leaf_filter(f, columns, location)
        if isinstance(f, BranchFilter):
            return self._validate_branch_filter(f, columns, location)
        return []

    def _validate_leaf_filter(
        self, f: LeafFilter, columns: Dict[str, Property], location: str
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []

        # (shape) operator must be a known OQO operator string.
        operator_known = f.operator in VALID_OPERATORS
        if not operator_known:
            errors.append(ValidationError(
                type="invalid_operator",
                message=f"'{f.operator}' is not a valid operator",
                location=f"{location}.operator",
            ))

        # (a) column registered on the entity.
        entry = columns.get(f.column_id)
        if entry is None:
            # Semantic (vector) search uses the OQL-canonical
            # `<field>.search.semantic` column (Case 30 / spec §search-modes), but
            # the engine exposes whole-document vector search under the single
            # registry capability `semantic.search` — the field prefix is surface
            # convention (the engine embeds the whole work, not just that field).
            # Map it to that capability so the canonical semantic OQO validates
            # against what the server actually runs and can be executed natively
            # via `/?oqo=`. (oxjob #363)
            if isinstance(f.column_id, str) and f.column_id.endswith(
                ".search.semantic"
            ):
                entry = columns.get("semantic.search")
        if entry is None:
            # "Did you mean" near-miss(es), mirroring the value-level suggestion
            # at _validate_closed_vocab. Makes the three causes of invalid_column
            # self-diagnosing — a wrong segment order (`<f>.exact.search`), a
            # plain typo, or a genuinely-unregistered field (no suggestion).
            suggestions = _suggest_columns(f.column_id, list(columns.keys()))
            hint = ""
            if suggestions:
                names = " or ".join(f"'{s}'" for s in suggestions)
                hint = f" Did you mean {names}?"
            errors.append(ValidationError(
                type="invalid_column",
                message=f"'{f.column_id}' is not a valid column.{hint}",
                location=f"{location}.column_id",
            ))
            # Can't check operator-fit / value-type without the column's type.
            return errors

        # (b) operator fits the property's type — only if the operator is a known one.
        if operator_known and not _operator_fits_column(
            f.operator, f.value, entry.operators
        ):
            errors.append(ValidationError(
                type="invalid_operator_for_column",
                message=(
                    f"Operator '{f.operator}' is not valid on column "
                    f"'{f.column_id}' (type '{entry.type}'; supports "
                    f"{entry.operators})"
                ),
                location=f"{location}.operator",
            ))

        # (c) value matches the property's type.
        if not _value_matches_type(entry.type, f.value):
            errors.append(ValidationError(
                type="invalid_value_type",
                message=(
                    f"Value {f.value!r} does not match the type "
                    f"'{entry.type}' of column '{f.column_id}'"
                ),
                location=f"{location}.value",
            ))
        # (d) value is a literal member of the column's closed vocabulary.
        #     Only fires when the type already matched (a non-string value on an
        #     enum column is already reported above) and the value isn't null/in
        #     collection (resolved elsewhere). Strict membership — no name->code.
        elif f.operator == "is" and f.value is not None:
            errors.extend(self._validate_value_domain(f, entry, location))

        return errors

    def _validate_value_domain(
        self, f: LeafFilter, entry: Property, location: str
    ) -> List[ValidationError]:
        """Value-domain validation, dispatched on the column's `entity_type`.
        Two tiers, both reusing a single declarative source so a value validates
        iff it could also be *produced* (rendered / parsed) by the same tables —
        no parallel allow-lists here (oxjob #363):

          Tier 1 — closed enumerated vocabs (countries / languages / sdgs /
            work-types / oa-statuses / continents): strict membership against the
            renderer's `config/<vocab>.yaml` `values` table. Rejects names and
            nonsense (`country is Canada`, `country is 42`).
          Tier 2 — open OpenAlex-ID entities (institutions / authors / sources /
            …): ID prefix/shape against the entity registry's `idRegex`. Rejects a
            right-shaped ID of the wrong type (`institution is W5` — a Works ID).
        """
        namespace = CLOSED_VOCAB_NAMESPACE.get(entry.entity_type)
        if namespace is not None:
            return self._validate_closed_vocab(f, entry, location, namespace)
        if entry.type == "openalex_id":
            return self._validate_openalex_id_shape(f, entry, location)
        return []

    def _validate_closed_vocab(
        self, f: LeafFilter, entry: Property, location: str, namespace: str
    ) -> List[ValidationError]:
        """Tier 1 — strict membership in a finite config-backed code vocab."""
        if is_vocab_member(namespace, f.value):
            return []
        # Build a "did you mean" when the user typed a display name (the common
        # footgun, e.g. `country is Canada` -> code `ca`); else a generic hint.
        suggestion = vocab_name_to_code(namespace, f.value) if isinstance(f.value, str) else None
        hint = f" Did you mean '{suggestion}'?" if suggestion else ""
        return [ValidationError(
            type="invalid_value",
            message=(
                f"Value {f.value!r} is not a valid {entry.entity_type} code "
                f"for column '{f.column_id}'.{hint}"
            ),
            location=f"{location}.value",
        )]

    def _validate_openalex_id_shape(
        self, f: LeafFilter, entry: Property, location: str
    ) -> List[ValidationError]:
        """Tier 2 — an `openalex_id`-typed value must carry the entity's ID
        prefix/shape. The shape is the entity registry's `idRegex` (declared in
        `config/<entity>.yaml`), so this never hand-maintains a prefix list. A
        column whose entity isn't a native-ID entity (unknown, or a slug/numeric
        id) has no shape to check and passes through."""
        ent = get_entity_type(entry.entity_type)
        if ent is None or not ent.is_native_id or ent.id_shape_ok(f.value):
            return []
        # Name the wrong type when the value is itself a valid OpenAlex ID of
        # another kind (the common slip, `institution is W5`) for a precise fix-it.
        hint = f" {entry.entity_type} IDs start with '{ent.id_prefix}' (e.g. {ent.id_prefix}12345)."
        if isinstance(f.value, str):
            m = re.match(r"\s*(?:https?://openalex\.org/)?([A-Za-z])\d+\s*\Z", f.value)
            other = entity_for_id_prefix(m.group(1)) if m else None
            if other and other != entry.entity_type:
                hint = (
                    f" {f.value!r} is an OpenAlex {other} ID; "
                    f"{entry.entity_type} IDs start with '{ent.id_prefix}'."
                )
        return [ValidationError(
            type="invalid_value",
            message=(
                f"Value {f.value!r} is not a valid {entry.entity_type} ID "
                f"for column '{f.column_id}'.{hint}"
            ),
            location=f"{location}.value",
        )]

    def _validate_branch_filter(
        self, f: BranchFilter, columns: Dict[str, Property], location: str
    ) -> List[ValidationError]:
        errors: List[ValidationError] = []

        if f.join not in ("and", "or"):
            errors.append(ValidationError(
                type="invalid_join",
                message=f"'{f.join}' is not a valid join operator. Use 'and' or 'or'.",
                location=f"{location}.join",
            ))

        if not f.filters:
            errors.append(ValidationError(
                type="empty_branch",
                message="Branch filter must have at least one sub-filter",
                location=f"{location}.filters",
            ))
        else:
            for i, sub_f in enumerate(f.filters):
                errors.extend(self._validate_filter(
                    sub_f, columns, f"{location}.filters[{i}]"
                ))

        return errors


def validate_oqo(oqo: OQO, config: Optional[Dict] = None) -> ValidationResult:
    """Validate an OQO against the entity-property catalog.

    `config` is accepted for backwards compatibility and ignored — validation is
    now driven entirely by the in-memory property catalog.
    """
    return OQOValidator().validate(oqo)
