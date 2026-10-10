"""Validator — checks an OQO against the live entity-property catalog.

Source of truth is `core.properties.ENTITY_PROPERTIES` (#331; formerly the #294
column registry): the per-entity catalog built at boot from the same `Field`
objects the filter layer executes. Validation answers, for each leaf filter,
three questions:

  (a) is `column_id` a real property on the OQO's `get_rows` entity? -> invalid_column
  (b) does `operator` fit that property's type?                     -> invalid_operator_for_column
  (c) does `value` match the property's type?                       -> invalid_value_type

Strict: every one of these is a hard error (the route returns 400). This catches
nonsense like `cited_by_count has 5` or `is_oa is 5` before it reaches ES.

Negation is the `is_negated` polarity bit, not an operator; the OQO->ES translator
applies it uniformly via `~q`, so it is NOT constrained here.
"""

import difflib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.entities import entity_for_id_prefix, get_entity_type
from core.fields import CollectionField, Property
from core.properties import (
    CAP_GROUP_BY,
    CAP_SORT,
    ENTITY_PROPERTIES,
    get_entity_capabilities,
    get_entity_columns,
    get_entity_properties,
)
from query_translation.oql_renderer import is_vocab_member, vocab_name_to_code
from query_translation.oqo import (
    OQO,
    LeafFilter,
    BranchFilter,
    FilterType,
    SortBy,
    VALID_OPERATORS,
    VALID_SORT_AGGREGATES,
    VALID_CORPORA,
    MEASURES,
    Measure,
    MeasureFilter,
    AffiliationFilter,
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


# OQO get_rows values that name the same property-catalog entity under a different
# label. Single-sourced from core.properties (#611 follow-up): the getters there
# are now alias-aware too, so oql_lang's registry fallback resolves `types`.
from core.properties import ENTITY_KEY_ALIASES as ENTITY_ALIASES  # noqa: E402

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
    "indexes": "indexes",
    # source-lists (oxjob #1205): `values:` in config/source-lists.yaml must list
    # every id the registry knows, or valid filters are rejected as invalid_value
    "source-lists": "source-lists",
    # study-designs (oxjob #1312): the seven PubMed-backed values in
    # config/study-designs.yaml; a slug outside them is invalid_value
    "study-designs": "study-designs",
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
    if operator == "has":
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

def _has_search_clause(filter_rows: List["FilterType"]) -> bool:
    """True if any leaf in the filter tree is a `*.search` (free-text) clause.

    Mirrors legacy `core.search.check_is_search_query`: a search query is present
    when a `?search=` (now mapped to a `default.search` filter row, #323 2a) or
    any `*.search` / `*.search.exact` filter is present (a quoted phrase and the
    keywords searches run on `.search.exact`; oxjob #1555 found relevance sort refused
    on them), across every legacy search key (default/title/abstract/fulltext/keyword/
    display_name/title_and_abstract/raw_*).
    """
    for f in filter_rows:
        if isinstance(f, BranchFilter):
            if _has_search_clause(f.filters):
                return True
        elif isinstance(f, LeafFilter):
            # `.search.exact` too: a quoted phrase, title-abstract-keywords (oxjob #1555)
            if isinstance(f.column_id, str) and f.column_id.endswith((".search", ".search.exact")):
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
        if oqo.walks or oqo.each:
            return self._validate_walked(oqo)
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
        # The unified per-property capability catalog (#450) — one source the
        # filter/sort/group_by/column gates all read from. `columns` (the rich
        # Property objects) is still used where type/operator detail is needed.
        capabilities = get_entity_capabilities(entity) or {}

        for i, f in enumerate(oqo.filter_rows):
            errors.extend(self._validate_filter(f, columns, f"filter_rows[{i}]"))

        # `sort_by` is an ordered list of sort keys (multi-column sort, #333).
        # Each key is validated on its own merits — exactly the single-sort rules
        # applied per element. Locations are indexed (`sort_by[i].…`) so a caller
        # can point at the offending key in a multi-column sort.
        has_search = _has_search_clause(oqo.filter_rows)
        # A calculated column sorts its groups (display sorting, oxjob #1530):
        # `sort=mean_fwci:desc`, `count`, `key`.
        measure_keys = ({m.key for m in oqo.calculate} | {"count", "key"}
                        if oqo.uses_pipeline else set())
        for i, key in enumerate(oqo.sort_by):
            if key.column_id in measure_keys and key.aggregate is None:
                continue
            errors.extend(self._validate_sort_key(
                key, i, columns, capabilities, has_search, bool(oqo.group_by),
                oqo.get_rows,
            ))

        if oqo.sample is not None:
            if not isinstance(oqo.sample, int) or isinstance(oqo.sample, bool) \
                    or oqo.sample < 1:
                errors.append(ValidationError(
                    type="invalid_sample",
                    message="Sample must be a positive integer",
                    location="sample",
                ))

        # Corpus selection (#481). Enum-gated; only `works` has an expansion
        # corpus, so a non-core corpus on any other entity is a no-op we warn on
        # rather than silently honoring.
        if oqo.corpus not in VALID_CORPORA:
            errors.append(ValidationError(
                type="invalid_corpus",
                message=(
                    f"'{oqo.corpus}' is not a valid corpus; expected one of "
                    f"{', '.join(sorted(VALID_CORPORA))}"
                ),
                location="corpus",
            ))
        elif oqo.corpus != "core" and oqo.get_rows != "works":
            warnings.append(ValidationError(
                type="corpus_ignored",
                message=(
                    f"corpus '{oqo.corpus}' only affects 'works'; ignored for "
                    f"'{oqo.get_rows}'"
                ),
                location="corpus",
            ))

        # group_by dimensions must be non-empty strings AND real columns.
        if len(oqo.group_by) > MAX_SPLITS:
            errors.append(ValidationError(
                type="too_many_splits",
                message=(f"A query can split its {oqo.get_rows} at most {MAX_SPLITS} "
                         f"times; this one splits {len(oqo.group_by)} times."),
                location="group_by",
            ))
        for i, g in enumerate(oqo.group_by):
            column_id = getattr(g, "column_id", None)
            if not g.is_plain:
                # the pipeline language's splits (oxjob #1530)
                errors.extend(self._validate_split(g, i, oqo, columns, capabilities))
                continue
            if not column_id or not isinstance(column_id, str):
                errors.append(ValidationError(
                    type="invalid_group_by",
                    message="group_by dimension must have a non-empty string column_id",
                    location=f"group_by[{i}].column_id",
                ))
            elif CAP_GROUP_BY not in capabilities.get(column_id, frozenset()):
                errors.append(ValidationError(
                    type="invalid_column",
                    message=(
                        f"'{column_id}' is not a groupable column on "
                        f"'{oqo.get_rows}'"
                    ),
                    location=f"group_by[{i}].column_id",
                ))

        for i, m in enumerate(oqo.calculate):
            errors.extend(self._validate_measure(m, f"calculate[{i}]", columns,
                                                 bool(oqo.group_by), oqo))

        # --- logistics layer (#318) ------------------------------------------

        # select: each entry must be a `column`-capable property on the entity.
        # Column capability (#450) is the result-schema projection surfaced through
        # the same capability catalog the sort/group_by gates use — see
        # core.properties.get_entity_columns / get_entity_capabilities.
        if oqo.select:
            selectable = get_entity_columns(entity)
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

    def _validate_walked(self, oqo: OQO) -> ValidationResult:
        """A query with walks (oxjob #1535) in three parts: the start on its own
        entity, the walks, and the splits, calculation and view on what the walks
        reached."""
        from dataclasses import replace
        from query_translation.oqo import result_entity
        start = self.validate(replace(oqo, walks=[], each=False, group_by=[], calculate=[],
                                      sort_by=[], select=[], per_page=None, page=None,
                                      cursor=None))
        errors = list(start.errors) + self._validate_walks(oqo)
        end = result_entity(oqo)
        if end != "works" and (oqo.group_by or any(m.measure != "count"
                                                   for m in oqo.calculate)):
            errors.append(ValidationError(
                type="invalid_walk", location="calculate" if not oqo.group_by else "group_by",
                message=(f"after walking to {end}, a query can count them (summarize using count); "
                         f"walk back to their works to split or measure")))
        if end != "works" and oqo.calculate and oqo.walks and oqo.walks[-1].each:
            errors.append(ValidationError(
                type="invalid_walk", location="calculate",
                message=(f"each row is one of the {end}, so there is nothing to count per "
                         f"row; count the set (get {end} of those works; then, summarize "
                         f"using count) or walk back to their works")))
        tail = OQO(get_rows=end, corpus="core", group_by=oqo.group_by,
                   calculate=[m for m in oqo.calculate] if end == "works" else [],
                   sort_by=oqo.sort_by, select=oqo.select, per_page=oqo.per_page,
                   page=oqo.page, cursor=oqo.cursor)
        rest = self.validate(tail)
        errors.extend(rest.errors)
        return ValidationResult(valid=not errors, errors=errors,
                                warnings=list(start.warnings) + list(rest.warnings))

    def _validate_sort_key(
        self,
        key: SortBy,
        index: int,
        columns: Dict[str, Property],
        capabilities: Dict[str, frozenset],
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
        elif key.column_id and CAP_SORT not in capabilities.get(
            key.column_id, frozenset()
        ):
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

    # -- the pipeline language (oxjob #1530) ---------------------------------
    def _validate_split(self, g, i, oqo, columns, capabilities) -> List[ValidationError]:
        loc = f"group_by[{i}]"
        errors: List[ValidationError] = []
        kinds = [k for k in ("values", "bins", "conditions") if getattr(g, k) is not None]
        if len(kinds) > 1:
            errors.append(ValidationError(
                type="invalid_group_by",
                message=f"A split takes one of values, bins or conditions, not {' and '.join(kinds)}.",
                location=loc))
            return errors
        if g.conditions is not None:
            if g.column_id is not None:
                errors.append(ValidationError(
                    type="invalid_group_by",
                    message="A split into conditions has no column_id.",
                    location=f"{loc}.column_id"))
            if not g.conditions or len(g.conditions) > MAX_LIST_ITEMS:
                errors.append(ValidationError(
                    type="invalid_list_length",
                    message=f"A split into conditions takes 1 to {MAX_LIST_ITEMS} conditions.",
                    location=f"{loc}.conditions"))
            for j, c in enumerate(g.conditions or []):
                errors.extend(self._validate_filter(c, columns, f"{loc}.conditions[{j}]"))
        elif not g.column_id or not isinstance(g.column_id, str):
            errors.append(ValidationError(
                type="invalid_group_by",
                message="This split needs a column_id.",
                location=f"{loc}.column_id"))
            return errors
        elif g.values is not None:
            if not g.values or len(g.values) > MAX_LIST_ITEMS:
                errors.append(ValidationError(
                    type="invalid_list_length",
                    message=f"A split by listed values takes 1 to {MAX_LIST_ITEMS} values.",
                    location=f"{loc}.values"))
            search = g.column_id.endswith(".search")
            for j, v in enumerate(g.values or []):
                vloc = f"{loc}.values[{j}]"
                if search:
                    if not isinstance(v, (LeafFilter, BranchFilter)):
                        errors.append(ValidationError(
                            type="invalid_group_by",
                            message="Each listed search is a filter tree on the search column.",
                            location=vloc))
                    else:
                        errors.extend(self._validate_filter(v, columns, vloc))
                elif isinstance(v, (LeafFilter, BranchFilter, dict, list)):
                    errors.append(ValidationError(
                        type="invalid_group_by",
                        message="Listed values are bare values of the split column.",
                        location=vloc))
                else:
                    errors.extend(self._validate_leaf_filter(
                        LeafFilter(g.column_id, v), columns, vloc))
        elif g.bins is not None:
            entry = columns.get(g.column_id)
            if entry is None or entry.type != "number":
                errors.append(ValidationError(
                    type="invalid_bins",
                    message=f"'{g.column_id}' isn't a number column, so it can't go in bins.",
                    location=f"{loc}.column_id"))
            at, of = g.bins.get("at"), g.bins.get("of")
            if (at is None) == (of is None):
                errors.append(ValidationError(
                    type="invalid_bins",
                    message="Bins take either 'at' (edges) or 'of' (a width).",
                    location=f"{loc}.bins"))
            elif at is not None:
                if (not isinstance(at, list) or not at or len(at) > MAX_LIST_ITEMS
                        or not all(_is_number(x) for x in at)
                        or any(b <= a for a, b in zip(at, at[1:]))):
                    errors.append(ValidationError(
                        type="invalid_bins",
                        message=f"Bin edges are 1 to {MAX_LIST_ITEMS} increasing numbers.",
                        location=f"{loc}.bins.at"))
            elif not _is_number(of) or of <= 0:
                errors.append(ValidationError(
                    type="invalid_bins",
                    message="A bin width is a number above 0.",
                    location=f"{loc}.bins.of"))
        elif CAP_GROUP_BY not in capabilities.get(g.column_id, frozenset()):
            errors.append(ValidationError(
                type="invalid_column",
                message=f"'{g.column_id}' is not a groupable column on '{oqo.get_rows}'",
                location=f"{loc}.column_id"))
        if g.where is not None:
            errors.extend(self._validate_group_where(g, g.where, f"{loc}.where", oqo, columns))
        return errors

    def _validate_group_where(self, g, f, loc, oqo, columns) -> List[ValidationError]:
        if isinstance(f, BranchFilter):
            errors: List[ValidationError] = []
            if f.join not in ("and", "or") or not f.filters:
                errors.append(ValidationError(
                    type="invalid_join",
                    message="A group filter branch needs 'and'/'or' and filters.",
                    location=loc))
            for j, c in enumerate(f.filters):
                errors.extend(self._validate_group_where(
                    g, c, f"{loc}.filters[{j}]", oqo, columns))
            return errors
        if isinstance(f, MeasureFilter):
            errors = self._validate_measure(Measure(f.measure, f.column_id), loc, columns, True)
            if f.measure == "percent_of_those":
                errors.append(ValidationError(
                    type="invalid_group_filter",
                    message="A group filter can't test percent of those works; filter on count.",
                    location=loc))
            if f.operator not in ("is", ">", ">=", "<", "<="):
                errors.append(ValidationError(
                    type="invalid_operator",
                    message=f"'{f.operator}' doesn't compare a calculation.",
                    location=f"{loc}.operator"))
            if not _is_number(f.value):
                errors.append(ValidationError(
                    type="invalid_value_type",
                    message="A calculation is compared with a number.",
                    location=f"{loc}.value"))
            return errors
        # a leaf on the group's own fields
        from query_translation.oql_lang import _group_entity
        group_entity = _group_entity(g, oqo.get_rows)
        if isinstance(f, AffiliationFilter):
            # `at [UBC](I141945490) since 2022`: an author's own record (oxjob #1555)
            errors = []
            if group_entity != "authors":
                errors.append(ValidationError(
                    type="invalid_group_filter",
                    message="An affiliation record with years belongs to authors.",
                    location=loc))
            if f.column_id not in ("affiliations.institution.lineage",
                                   "affiliations.institution.country_code") or not f.value:
                errors.append(ValidationError(
                    type="invalid_group_filter",
                    message="An affiliation record names an institution or a country.",
                    location=loc))
            if f.min_years is not None and (not isinstance(f.min_years, int)
                                            or isinstance(f.min_years, bool) or f.min_years < 1):
                errors.append(ValidationError(
                    type="invalid_value", message="'min_years' is a whole number of years.",
                    location=f"{loc}.min_years"))
            for k in ("since", "through"):
                v = getattr(f, k)
                if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                    errors.append(ValidationError(
                        type="invalid_value_type",
                        message=f"'{k}' is a year.", location=f"{loc}.{k}"))
            if (isinstance(f.since, int) and isinstance(f.through, int)
                    and f.since > f.through):
                errors.append(ValidationError(
                    type="invalid_value",
                    message="The years run from the earlier to the later.",
                    location=loc))
            return errors
        if group_entity is None:
            return [ValidationError(
                type="invalid_group_filter",
                message="These groups have no fields of their own; filter by a calculation.",
                location=loc)]
        if f.column_id in GROUP_FILTER_RELATIONS:
            want = GROUP_FILTER_RELATIONS[f.column_id]
            if group_entity != want:
                return [ValidationError(
                    type="invalid_group_filter",
                    message=f"'{f.column_id}' filters {want} groups, not {group_entity}.",
                    location=loc)]
            return []
        if f.column_id == "ids.openalex":
            # `that country is not [Iran](IR)`: the group itself, matched on its bucket
            # key by the engine for every kind of group (countries have no id column)
            return []
        g_entity = _resolve_property_entity(group_entity)
        g_columns = get_entity_properties(g_entity) if g_entity else None
        if not g_columns:
            return [ValidationError(
                type="invalid_group_filter",
                message=f"{group_entity} groups have no fields to filter on.",
                location=loc)]
        return self._validate_filter(f, g_columns, loc)

    def _validate_measure(self, m, loc, columns, has_split, oqo=None) -> List[ValidationError]:
        if m.measure not in MEASURES:
            return [ValidationError(
                type="invalid_measure",
                message=f"'{m.measure}' isn't a calculation; use one of {', '.join(MEASURES)}.",
                location=f"{loc}.measure")]
        if m.measure == "value":
            # a split's own field, shown beside each group: some split must be by
            # things that have it
            from query_translation.oql_lang import _group_entity
            for g in (oqo.group_by if oqo is not None else []):
                ge = _group_entity(g, oqo.get_rows)
                ge_key = _resolve_property_entity(ge) if ge else None
                props = get_entity_properties(ge_key) if ge_key else None
                # any field of the groups' own but a search (oxjob #1555: `last known
                # institution` beside authors, as well as `h-index`)
                if props and m.column_id in props and \
                        "search" not in (props[m.column_id].operators or []):
                    return []
            return [ValidationError(
                type="invalid_measure",
                message=(f"'{m.column_id}' isn't a field of any split's groups; a "
                         f"group's own field needs a split by things that have it."),
                location=f"{loc}.column_id")]
        if m.measure in ("count", "percent_of_those"):
            if m.column_id is not None:
                return [ValidationError(
                    type="invalid_measure",
                    message=f"'{m.measure}' takes no column.",
                    location=f"{loc}.column_id")]
            if m.measure == "percent_of_those" and not has_split:
                return [ValidationError(
                    type="invalid_measure",
                    message="percent of those works needs a split (a group's share of its set).",
                    location=loc)]
            return []
        entry = columns.get(m.column_id) if m.column_id else None
        want = "boolean" if m.measure == "percent" else "number"
        if (entry is not None and m.measure in ("min", "max")
                and entry.type in ("date", "datetime")):
            return []   # the earliest / latest date
        if entry is None or entry.type != want:
            kind = "a yes/no" if want == "boolean" else "a number"
            return [ValidationError(
                type="invalid_measure",
                message=f"'{m.measure}' takes {kind} column; '{m.column_id}' isn't one.",
                location=f"{loc}.column_id")]
        return []

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

        if f.operator == "in" or isinstance(f.value, OQO):
            return self._validate_query_set(f, columns, location)
        if f.column_id in GROUP_FILTER_RELATIONS:
            # co-author / collaborator at the top level (oxjob #1535): only on the
            # things they relate, and only to ids of that kind
            want = GROUP_FILTER_RELATIONS[f.column_id]
            ent = _resolve_property_entity(want)
            if ent is None or columns is not get_entity_properties(ent):
                return [ValidationError(
                    type="invalid_column", location=f"{location}.column_id",
                    message=(f"'{f.column_id}' filters {want} (get {want} where "
                             f"{'co-author' if want == 'authors' else 'collaborator'} is ...)"))]
            if f.operator != "is" or not isinstance(f.value, str):
                return [ValidationError(
                    type="invalid_value_type", location=f"{location}.value",
                    message=f"'{f.column_id}' takes {want[:-1]} ids")]
            return []

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

    def _validate_query_set(
        self, f: LeafFilter, columns: Dict[str, Property], location: str
    ) -> List[ValidationError]:
        """`author is in (<a whole query>)`, `it cites works in (<a whole query>)`
        (oxjob #1535): operator `in`, a nested OQO that returns the column's kind of
        thing, one level deep, ending at the things (no splits or calculations)."""
        from query_translation.oqo import has_query_value, result_entity
        from query_translation.oql_lang import entity_type_for_column
        def err(kind, msg, where=".value"):
            return [ValidationError(type=kind, message=msg, location=location + where)]
        if f.operator != "in" or not isinstance(f.value, OQO):
            return err("invalid_query_set",
                       "a whole query as a value takes the operator 'in' (and 'in' takes a query)",
                       ".operator")
        if f.column_id not in columns and f.column_id not in ("referenced_works", "cited_by",
                                                               "related_to"):
            return err("invalid_column", f"'{f.column_id}' is not a valid column.", ".column_id")
        inner = f.value
        if inner.calculate or inner.group_by:
            return err("invalid_query_set",
                       "a query in parentheses must return things, not numbers or groups")
        if any(has_query_value(x) for x in inner.filter_rows) or any(
                w.where is not None and has_query_value(w.where) for w in inner.walks):
            return err("invalid_query_set", "a query in parentheses can't hold another one")
        want = ("works" if f.column_id in ("referenced_works", "cited_by", "related_to")
                else entity_type_for_column(f.column_id, "works"))
        got = result_entity(inner)
        if want is not None and got != want:
            return err("invalid_query_set",
                       f"'{f.column_id}' takes {want}; the query returns {got}")
        sub = OQOValidator().validate(inner)
        return [ValidationError(type=e.type, message=e.message,
                                location=f"{location}.value.{e.location}")
                for e in sub.errors]

    def _validate_walks(self, oqo: OQO) -> List[ValidationError]:
        """The walks (oxjob #1535): each link is a walkable works column, a walk's
        `where` uses the walked things' own fields, one walk out and one back, and
        `each` on a start only for things that aren't works."""
        from query_translation.walks import (LINK_ENTITY, WHERE_ENTITIES, link_for)
        errors: List[ValidationError] = []
        cur = oqo.get_rows
        if oqo.each and cur == "works":
            errors.append(ValidationError(type="invalid_walk", location="each",
                          message="'each' starts from things that aren't works"))
        outs = backs = 0
        for i, w in enumerate(oqo.walks):
            loc = f"walks[{i}]"
            if w.to is not None:
                backs += 1
                if w.to != "works":
                    errors.append(ValidationError(type="invalid_walk", location=f"{loc}.to",
                                  message="a walk back goes to works"))
                elif cur == "works" or link_for(cur) is None:
                    errors.append(ValidationError(type="invalid_walk", location=loc,
                                  message=f"there are no {cur} to walk back from"))
                cur = "works"
            else:
                outs += 1
                walked = LINK_ENTITY.get(w.column_id)
                if walked is None:
                    errors.append(ValidationError(type="invalid_walk", location=f"{loc}.column_id",
                                  message=f"'{w.column_id}' isn't a walkable link"))
                    return errors
                if cur != "works":
                    errors.append(ValidationError(type="invalid_walk", location=loc,
                                  message="a walk out starts from works"))
                if w.where is not None and walked not in WHERE_ENTITIES:
                    errors.append(ValidationError(type="invalid_walk", location=f"{loc}.where",
                                  message=f"{walked} have no fields of their own to filter on"))
                    w = None
                cur = walked
            if w is not None and w.where is not None:
                ent = _resolve_property_entity(cur)
                cols = get_entity_properties(ent) if ent else {}
                errors.extend(self._validate_filter(w.where, cols, f"{loc}.where"))
        if outs > 1 or backs > 1:
            errors.append(ValidationError(type="invalid_walk", location="walks",
                          message="a query walks out once and back once (for now)"))
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

        Collection references pass BOTH tiers through: a pure `col_…` / `!col_…`
        value on an entity-typed column is the cross-type collection filter
        (#266; worked example 49 `authorships.countries: col_eu27`, and the same
        shape on classic REST `filter=`). It is execution-resolved —
        `core.filter.resolve_collection_for_field` enforces the collection's
        entity_type against the column's and expands it to member values — so
        the value-domain tiers must mirror execution's exact detection
        (`CollectionField.COLLECTION_ID_RE`) rather than reject a value the
        engine executes. (Dispatch (c)/(d) above already noted collections are
        "resolved elsewhere" but only exempted the `in collection` OPERATOR,
        not a `col_…` VALUE under the default `is` — fixed 2026-07-20.)
        """
        if isinstance(f.value, str) and CollectionField.COLLECTION_ID_RE.match(f.value):
            return []
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


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# Group-filter relations (oxjob #1530): co-authorship tests, valid only on groups
# of the named entity. Not registry columns (they need a lookup call).
GROUP_FILTER_RELATIONS = {"co_author": "authors", "collaborator": "institutions"}
MAX_SPLITS = 3
MAX_LIST_ITEMS = 100


def validate_oqo(oqo: OQO, config: Optional[Dict] = None) -> ValidationResult:
    """Validate an OQO against the entity-property catalog.

    `config` is accepted for backwards compatibility and ignored — validation is
    now driven entirely by the in-memory property catalog.
    """
    return OQOValidator().validate(oqo)
