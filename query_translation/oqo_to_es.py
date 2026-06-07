"""
OQO → Elasticsearch translator.

Walks an OQO tree and emits a single `elasticsearch_dsl.Q` object that can be
applied to a `Search` via `s.filter(q)`.

The leaf-level translation reuses each entity's existing field registry
(`core/fields.py` `Field` subclasses) by re-encoding the OQO operator + value
into the URL value-string shape that `field.build_query()` already understands.
Boolean joins (AND/OR) and the `is_negated` polarity bit are wrapped at the
translator level via `Q("bool", ...)` / `~Q(...)`.

The job this serves is #306 — accepting OQO directly at `/query` without the
lossy round-trip through the OXURL surface (#303, #305).
"""

from typing import Optional

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.utils import get_field
from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


class OQOTranslationError(APIQueryParamsError):
    """Raised when an OQO can't be translated to an ES query."""

    pass


def oqo_to_q(oqo: OQO, fields_dict) -> Optional[Q]:
    """Translate the filter portion of an OQO into a single ES `Q` object.

    Returns None if the OQO has no filters (caller should still execute the
    Search without a filter — pagination/sort/group_by still apply).

    Multiple top-level entries in `oqo.filter_rows` are AND-combined, mirroring
    the URL surface where each `filter=` clause is applied via `s.filter(q)`.
    """
    if not oqo.filter_rows:
        return None

    child_queries = [_translate(f, fields_dict) for f in oqo.filter_rows]
    child_queries = [q for q in child_queries if q is not None]

    if not child_queries:
        return None
    if len(child_queries) == 1:
        return child_queries[0]
    return Q("bool", must=child_queries)


def _is_scoring_search_leaf(f: FilterType) -> bool:
    """A top-level `.search` leaf that should be applied in *query* (scoring)
    context, mirroring legacy. Negated search leaves and search leaves nested in
    branches are NOT lifted — they stay in filter context (correct recall,
    no scoring contribution), which is rare in the real corpus.
    """
    return (
        isinstance(f, LeafFilter)
        and not f.is_negated
        and isinstance(f.column_id, str)
        and f.column_id.endswith(".search")
    )


def oqo_to_search_and_filter_q(oqo: OQO, fields_dict, scoring: bool = True):
    """Split an OQO into `(search_q, filter_q)` so the executor can apply search
    in *query* (scoring) context and exact filters in *filter* context — exactly
    what legacy `construct_query` does (`s.query(search)` + `s.filter(filters)`).

    Why this exists: applying a `.search` clause via `s.filter()` runs it in
    filter context, where `_score` is uniform — so sorting by `_score`
    (relevance) is a no-op and search results come back in the secondary-sort
    order (e.g. publication_date) instead of by relevance. Legacy avoids this by
    scoring the search query. (#323: caught by prod differential check.)

    Only TOP-LEVEL, non-negated `.search` leaves are lifted to scoring; anything
    else (exact filters, branches, negated/ nested search) goes to `filter_q`.
    When `scoring=False` (sampling — legacy applies search via `s.filter` when a
    `sample` is set), every row goes to `filter_q`, reproducing legacy exactly.
    """
    if scoring:
        search_rows = [f for f in oqo.filter_rows if _is_scoring_search_leaf(f)]
        filter_rows = [f for f in oqo.filter_rows if not _is_scoring_search_leaf(f)]
    else:
        search_rows, filter_rows = [], list(oqo.filter_rows)

    def _combine(rows):
        qs = [_translate(f, fields_dict) for f in rows]
        qs = [q for q in qs if q is not None]
        if not qs:
            return None
        if len(qs) == 1:
            return qs[0]
        return Q("bool", must=qs)

    return _combine(search_rows), _combine(filter_rows)


def _translate(node: FilterType, fields_dict) -> Optional[Q]:
    if isinstance(node, LeafFilter):
        return _translate_leaf(node, fields_dict)
    if isinstance(node, BranchFilter):
        return _translate_branch(node, fields_dict)
    raise OQOTranslationError(
        f"Unknown filter node type: {type(node).__name__}"
    )


def _translate_branch(branch: BranchFilter, fields_dict) -> Optional[Q]:
    if branch.join not in ("and", "or"):
        raise OQOTranslationError(
            f"Invalid branch join '{branch.join}' — must be 'and' or 'or'."
        )
    if not branch.filters:
        raise OQOTranslationError("Branch filter has no children.")

    child_queries = [_translate(f, fields_dict) for f in branch.filters]
    child_queries = [q for q in child_queries if q is not None]
    if not child_queries:
        return None

    if branch.join == "and":
        if len(child_queries) == 1:
            q = child_queries[0]
        else:
            q = Q("bool", must=child_queries)
    else:  # "or"
        q = Q("bool", should=child_queries, minimum_should_match=1)

    if branch.is_negated:
        q = ~q
    return q


def _translate_leaf(leaf: LeafFilter, fields_dict) -> Q:
    try:
        field = get_field(fields_dict, leaf.column_id)
    except APIQueryParamsError as e:
        # Re-raise with the same shape so the route returns 400, not 500.
        raise OQOTranslationError(str(e))

    url_value = _encode_leaf_value(leaf)
    # Field instances are stateful; build_query() reads self.value. This matches
    # the existing core/filter.py:filter_records pattern.
    field.value = url_value
    try:
        q = field.build_query()
    except APIQueryParamsError:
        raise
    except Exception as e:
        # Unexpected build_query failure — surface as 400, not 500.
        raise OQOTranslationError(
            f"Could not build query for column_id '{leaf.column_id}' "
            f"with value {leaf.value!r}: {e}"
        )

    if leaf.is_negated:
        q = ~q
    return q


def _encode_leaf_value(leaf: LeafFilter) -> str:
    """Re-encode an OQO leaf into the URL value-string shape `build_query()` consumes.

    OQO carries the operator on the leaf; the URL surface carries it inline in
    the value string (e.g. `">2020"`, `"2020-"`, `"-2024"`, `"null"`). We translate
    the operator + bare value into the URL form so the field's `build_query()`
    can dispatch as it already does on the URL path.

    Special-case `None` (`null`) and booleans (`true`/`false`) since the URL
    value strings carry those as literal text.
    """
    op = leaf.operator
    v = leaf.value

    # None / null → URL form is the literal "null".
    if v is None:
        if op != "is":
            raise OQOTranslationError(
                f"Operator '{op}' is not valid with a null value "
                f"on column_id '{leaf.column_id}'."
            )
        return "null"

    # Booleans → literal "true"/"false". OQO emits these as native bools; URL
    # surface uses lowercase strings.
    if isinstance(v, bool):
        if op != "is":
            raise OQOTranslationError(
                f"Operator '{op}' is not valid with a boolean value "
                f"on column_id '{leaf.column_id}'."
            )
        return "true" if v else "false"

    # Everything else: stringify the bare value, then add the operator prefix.
    s = str(v)

    if op == "is" or op == "contains":
        return s
    # Collection membership: the URL surface carries the bare col_… value (the
    # field's build_query handles resolution — same-type via CollectionField, which
    # resolves through core/collection_resolver). (oxjob #363)
    if op == "in collection":
        return s
    if op == ">":
        return f">{s}"
    if op == "<":
        return f"<{s}"
    if op == ">=":
        # RangeField gte form is "N-"  (trailing dash). Note `>=N` is the canonical
        # OQO operator but the URL surface uses the range form.
        return f"{s}-"
    if op == "<=":
        # RangeField lte form is "-N" (leading dash).
        return f"-{s}"

    raise OQOTranslationError(
        f"Unknown operator '{op}' on column_id '{leaf.column_id}'. "
        f"Valid operators: is, >, >=, <, <=, contains, in collection."
    )
