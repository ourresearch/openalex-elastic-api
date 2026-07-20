import re

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.fields import CollectionField, TermField, _canonicalize_entity_ids
from core.collection_resolver import resolve_collection
from core.utils import get_field
from settings import MAX_IDS_IN_FILTER


def filter_records(fields_dict, filter_params, s, sample=None):
    if filter_params:
        s, filter_params = _apply_collection_filters(fields_dict, filter_params, s)
        s, filter_params = _apply_cross_type_collection_filters(fields_dict, filter_params, s)
    for filter in filter_params:
        for key, value in filter.items():
            if key == 'include_xpac' or key == 'include-xpac':
                continue
            field = get_field(fields_dict, key)

            # Quoted non-search values are single exact values (spaces are
            # literal, not AND operators).  Strip the quotes and skip the
            # space-split AND logic below.
            is_quoted = (
                value.startswith('"') and value.endswith('"')
                and "search" not in field.param
            )
            if is_quoted:
                value = value[1:-1]

            # multiple OR queries have | in the param values
            if "|" in value:
                s = handle_or_query(field, fields_dict, s, value, sample)

            # multiple AND queries have + in the param values which is converted to a space
            elif (
                " " in value
                and not is_quoted
                and "search" not in field.param
                and type(field).__name__ != "RangeField"
                and type(field).__name__ != "BooleanField"
            ):
                s = handle_and_query(field, s, value)

            # everything else is a normal and query
            else:
                field.value = value
                q = field.build_query()
                if sample and "search" in field.param:
                    s = s.filter(q)
                elif "search" in field.param:
                    s = s.query(q)
                else:
                    s = s.filter(q)
    return s


BLOCKED_AUTHOR_IDS = {"A9999999999", "a9999999999"}


def handle_or_query(field, fields_dict, s, value, sample):
    or_queries = []

    # Silently filter out blocked author IDs (e.g., null author placeholder)
    if field.param in ("authorships.author.id", "author.id"):
        values = value.split("|")
        values = [v for v in values if v.upper().replace("HTTPS://OPENALEX.ORG/", "") not in BLOCKED_AUTHOR_IDS]
        if not values:
            # All values were filtered out, return unchanged search
            return s
        value = "|".join(values)

    if len(value.split("|")) > MAX_IDS_IN_FILTER:
        raise APIQueryParamsError(
            f"Maximum number of values exceeded for {field.param}. Decrease values to {MAX_IDS_IN_FILTER} or "
            f"below, or consider downloading the full dataset at "
            f"https://developers.openalex.org/download/snapshot-format"
        )

    # raise error if trying to use | between filters like filter=institutions.country_code:fr|host_venue.issn:0957-1558
    fields = fields_dict.keys()
    for filter_field in fields:
        if filter_field in value:
            if filter_field and re.search(rf"{filter_field}:", value):
                raise APIQueryParamsError(
                    f"It looks like you're trying to do an OR query between filters and it's not supported. \n"
                    f"You can do this: institutions.country_code:fr|en, but not this: institutions.country_code:gb|host_venue.issn:0957-1558. \n"
                    f"Problem value: {value}"
                )

    if value.startswith("!"):
        # negate everything in values after !, like: NOT (42 or 43)
        for or_value in value.split("|"):
            or_value = or_value.replace("!", "")
            field.value = or_value
            q = field.build_query()
            not_query = ~Q("bool", must=q)
            if sample and "search" in field.param:
                s = s.filter(not_query)
            elif "search" in field.param:
                s = s.query(not_query)
            else:
                s = s.filter(not_query)
    else:
        # standard OR query, like: 42 or 43
        # Check if this is a TermField and use the more efficient terms query
        if isinstance(field, TermField):
            # Use the optimized terms query for TermField
            values = value.split("|")
            for or_value in values:
                if or_value.startswith("!"):
                    raise APIQueryParamsError(
                        f"The ! operator can only be used at the beginning of an OR query, "
                        f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                        f"value: {or_value}"
                    )
            # Build a single terms query instead of multiple term queries
            combined_or_query = field.build_terms_query(values)
            if sample and "search" in field.param:
                s = s.filter(combined_or_query)
            elif "search" in field.param:
                s = s.query(combined_or_query)
            else:
                s = s.filter(combined_or_query)
        else:
            # Fall back to the original bool/should approach for other field types
            for or_value in value.split("|"):
                if or_value.startswith("!"):
                    raise APIQueryParamsError(
                        f"The ! operator can only be used at the beginning of an OR query, "
                        f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                        f"value: {or_value}"
                    )
                field.value = or_value
                q = field.build_query()
                or_queries.append(q)
            combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
            if sample and "search" in field.param:
                s = s.filter(combined_or_query)
            elif "search" in field.param:
                s = s.query(combined_or_query)
            else:
                s = s.filter(combined_or_query)
    return s


def handle_and_query(field, s, value):
    and_queries = []

    if len(value.split(" ")) > MAX_IDS_IN_FILTER:
        raise APIQueryParamsError(
            f"Maximum number of values exceeded for {field.param}. Decrease values to {MAX_IDS_IN_FILTER} or "
            f"below, or consider downloading the full dataset at "
            f"https://developers.openalex.org/download/snapshot-format"
        )

    for and_value in value.split(" "):
        field.value = and_value
        q = field.build_query()
        and_queries.append(q)
    combined_and_query = Q("bool", must=and_queries)
    s = s.filter(combined_and_query)
    return s


# Per-request hard caps for the `collection:` filter. Only one `collection:` filter is
# allowed per request — UI restriction (oxjob #228), also defense-in-depth
# against perf risks of unioning multiple 1000-entity lists into a single ES
# `terms` clause. Defenses against DoS-via-request-amplification: each collection
# triggers an outbound HTTP resolve to users-api, and each resolved ID list
# becomes part of an ES `terms` clause.
MAX_COLLECTIONS_PER_REQUEST = 1
MAX_RESOLVED_IDS_PER_REQUEST = 10_000


def _apply_collection_filters(fields_dict, filter_params, s):
    """Pre-pass: resolve a single positive or negated `collection:` filter into an ES
    `terms` clause on entity id.

    Only one `collection:` filter is allowed per request (oxjob #228, multi-collection
    intersection removed); >1 and `|`-OR within a value both 400 fail-fast.

    Returns (search, remaining filter_params) with the `collection:` entry
    consumed.
    """
    positives = []
    negatives = []
    other = []
    for f in filter_params:
        if "collection" in f and len(f) == 1:
            value = f["collection"] or ""
            # OR within one collection: filter (e.g. `collection:L1|L2`) is rejected —
            # would union the ID lists and could blow past MAX_RESOLVED_IDS.
            if "|" in value:
                raise APIQueryParamsError(
                    "OR (pipe) between collection values is not supported. "
                    "Only one collection: filter is allowed per request."
                )
            if not CollectionField.COLLECTION_ID_RE.match(value):
                raise APIQueryParamsError(
                    f"'{value}' is not a valid collection id (expected 'col_...')."
                )
            if value.startswith("!"):
                negatives.append(value[1:])
            else:
                positives.append(value)
        else:
            other.append(f)

    # Dedupe (preserves first-seen order) so a repeated `collection:L1` is one call,
    # not N. Done before the count cap so the cap reflects distinct collections.
    positives = list(dict.fromkeys(positives))
    negatives = list(dict.fromkeys(negatives))

    if len(positives) + len(negatives) > MAX_COLLECTIONS_PER_REQUEST:
        raise APIQueryParamsError(
            "Only one collection: filter is allowed per request."
        )

    collection_field = fields_dict.get("collection")
    if not isinstance(collection_field, CollectionField) and (positives or negatives):
        # Endpoint doesn't expose the `collection:` filter. Return the original
        # filter_params so the normal loop produces the standard "not a valid
        # field" error for the collection entries.
        return s, filter_params

    endpoint_entity_type = collection_field.entity_type if collection_field else None

    def _check_type(collection_id, collection_entity_type):
        if collection_entity_type and collection_entity_type != endpoint_entity_type:
            raise APIQueryParamsError(
                f"collection {collection_id} is type '{collection_entity_type}', "
                f"not valid for /{endpoint_entity_type}"
            )

    total_ids = 0

    def _budget(count):
        nonlocal total_ids
        total_ids += count
        if total_ids > MAX_RESOLVED_IDS_PER_REQUEST:
            raise APIQueryParamsError(
                f"collection: filter resolved to too many entities "
                f"(max {MAX_RESOLVED_IDS_PER_REQUEST})"
            )

    # Positive collection (at most one — enforced above).
    if positives:
        lid = positives[0]
        etype, ids = resolve_collection(lid)
        _budget(len(ids))
        # Unknown / deleted collection → empty `terms` (silently matches 0; spec).
        if etype is None:
            ids = []
        else:
            _check_type(lid, etype)
        s = s.filter(Q("terms", id=_canonicalize_entity_ids(ids, endpoint_entity_type)))

    # Negated collection (at most one — enforced above, and only when positives is empty).
    if negatives:
        lid = negatives[0]
        etype, ids = resolve_collection(lid)
        if etype is not None:
            _check_type(lid, etype)
            _budget(len(ids))
            s = s.filter(
                ~Q("bool", must=Q("terms", id=_canonicalize_entity_ids(ids, endpoint_entity_type)))
            )

    return s, other


def _value_has_collection_ref(value):
    """True if `value` contains a `col_xxx` segment anywhere."""
    parts = re.split(r"[ |]", value or "")
    return any(CollectionField.COLLECTION_ID_RE.match(p) for p in parts)


def _value_is_pure_collection_ref(value):
    """True iff value is exactly a single `col_xxx` or `!col_xxx`."""
    return bool(CollectionField.COLLECTION_ID_RE.match(value or ""))


def resolve_collection_for_field(field, collection_id):
    """Resolve a cross-type `col_…` reference against an entity-id `field`,
    enforcing that the collection's entity_type matches the field's.

    Shared by the URL pre-pass (`_apply_cross_type_collection_filters`) and the
    OQO execution path (`query_translation/oqo_to_es`) so both run the *same*
    resolver call + type check and can't silently diverge (oxjob #363). Before
    this, the OQO path read a bare `col_…` as a literal OpenAlex ID and matched
    ~zero — see `query_translation/oqo_to_es._cross_type_collection_query`.

    Returns `(entity_type, entity_ids)`:
      - `(None, [])` for an unknown / deleted collection (the caller matches zero
        / no-ops per spec).
    Raises `APIQueryParamsError` if the resolved collection's entity_type doesn't
    match `field.entity_type`.

    `collection_id` must be the bare id (no leading `!`); negation, the match-zero
    empty clause, and the per-request ID budget are the caller's concern.
    """
    etype, ids = resolve_collection(collection_id)
    if etype is not None and etype != field.entity_type:
        raise APIQueryParamsError(
            f"collection {collection_id} is type '{etype}', not valid for "
            f"the `{field.param}` filter (expects '{field.entity_type}')."
        )
    return etype, ids


def _apply_cross_type_collection_filters(fields_dict, filter_params, s):
    """Pre-pass: resolve `<entity-id-field>:col_xxx` filters into terms clauses on
    the target field. Runs after `_apply_collection_filters`.

    Detection: any filter clause whose value is exactly `col_xxx` or `!col_xxx`,
    against a Field instance with a non-None `entity_type`.

    Rejects (Phase 0 decisions, oxjob #266):
    - `col_xxx` mixed with literal IDs or other refs via `|` / ` ` in one value
    - Multiple `col_xxx` entries on the same field across filter clauses (v1)
    - `col_xxx` on a field with no `entity_type` (defense)
    - `col_xxx` whose resolved entity_type doesn't match the field's

    Behavior:
    - Unknown / deleted collection → positive: match zero; negation: no-op (spec)
    - Negation `!col_xxx` → wrap the resolved terms clause in `bool.must_not`
    - Type check happens before the budget consumes IDs

    Returns (search, remaining filter_params).
    """
    cross = []         # (field, raw_value)
    remaining = []

    for f in filter_params:
        if len(f) != 1:
            remaining.append(f)
            continue
        key, value = next(iter(f.items()))
        if key in ("include_xpac", "include-xpac"):
            remaining.append(f)
            continue
        if not _value_has_collection_ref(value):
            remaining.append(f)
            continue
        if not _value_is_pure_collection_ref(value):
            raise APIQueryParamsError(
                f"'{value}' mixes a collection reference (col_...) with literal "
                f"values or another reference. v1 supports only a single "
                f"col_... per filter clause (no `|` / space mixing)."
            )
        field = fields_dict.get(key) or fields_dict.get(key.replace("-", "_"))
        if field is None:
            # Unknown field — let the main loop produce the standard
            # "not a valid filter field" error.
            remaining.append(f)
            continue
        if field.entity_type is None:
            raise APIQueryParamsError(
                f"The `{key}` filter does not support cross-type collection "
                f"references (col_...). Use a same-type `collection:` filter "
                f"or a literal value list."
            )
        cross.append((field, value))

    if not cross:
        return s, remaining

    # Phase 0 decision: one col_... per (field, request) in v1.
    seen = {}
    for field, value in cross:
        if field.param in seen:
            raise APIQueryParamsError(
                f"Multiple collection references for the `{field.param}` filter "
                f"are not supported in v1."
            )
        seen[field.param] = value

    total_ids = 0

    def _budget(count):
        nonlocal total_ids
        total_ids += count
        if total_ids > MAX_RESOLVED_IDS_PER_REQUEST:
            raise APIQueryParamsError(
                f"cross-type collection filters resolved to too many entities "
                f"(max {MAX_RESOLVED_IDS_PER_REQUEST})"
            )

    for field, value in cross:
        negate = value.startswith("!")
        collection_id = value[1:] if negate else value

        etype, ids = resolve_collection_for_field(field, collection_id)

        # Unknown / deleted collection:
        # - positive: silently match zero (spec)
        # - negation: silently no-op (filter matches all docs)
        if etype is None:
            if negate:
                continue
            s = s.filter(Q("terms", **{field.es_field(): []}))
            continue

        _budget(len(ids))

        if not ids:
            if negate:
                continue
            s = s.filter(Q("terms", **{field.es_field(): []}))
            continue

        clause = field.build_terms_query(ids)
        if negate:
            s = s.filter(~Q("bool", must=clause))
        else:
            s = s.filter(clause)

    return s, remaining
