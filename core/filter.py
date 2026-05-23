import re

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.fields import LabelField, TermField, _canonicalize_entity_ids
from core.label_resolver import resolve_label
from core.utils import get_field
from settings import MAX_IDS_IN_FILTER


def filter_records(fields_dict, filter_params, s, sample=None):
    if filter_params:
        s, filter_params = _apply_label_filters(fields_dict, filter_params, s)
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


# Per-request hard caps for the `label:` filter. Defenses against DoS-via-
# request-amplification: each label triggers an outbound HTTP resolve to
# users-api, and each resolved ID list becomes part of an ES `terms` clause.
MAX_LABELS_PER_REQUEST = 8
MAX_RESOLVED_IDS_PER_REQUEST = 10_000


def _apply_label_filters(fields_dict, filter_params, s):
    """Pre-pass: collapse multiple positive `label:` filters into one ES `terms`
    clause built from the server-side intersection of their entity-ID lists.

    Negated `label:!L1` filters are passed through to the normal LabelField
    path (each becomes its own `NOT terms` clause). All label filters are
    validated to match the endpoint's entity type; mismatched types 400.

    Returns (search, remaining filter_params) with all `label:` entries
    consumed.
    """
    positives = []
    negatives = []
    other = []
    for f in filter_params:
        if "label" in f and len(f) == 1:
            value = f["label"]
            if not LabelField.LABEL_ID_RE.match(value or ""):
                raise APIQueryParamsError(
                    f"'{value}' is not a valid label id (expected 'label-...')."
                )
            if value.startswith("!"):
                negatives.append(value[1:])
            else:
                positives.append(value)
        else:
            other.append(f)

    # Dedupe (preserves first-seen order) so a repeated `label:L1` is one call,
    # not N. Done before the count cap so the cap reflects distinct labels.
    positives = list(dict.fromkeys(positives))
    negatives = list(dict.fromkeys(negatives))

    if len(positives) + len(negatives) > MAX_LABELS_PER_REQUEST:
        raise APIQueryParamsError(
            f"too many label: filters in one request "
            f"(max {MAX_LABELS_PER_REQUEST})"
        )

    label_field = fields_dict.get("label")
    if not isinstance(label_field, LabelField) and (positives or negatives):
        # Endpoint doesn't expose the `label:` filter. Return the original
        # filter_params so the normal loop produces the standard "not a valid
        # field" error for the label entries.
        return s, filter_params

    endpoint_entity_type = label_field.entity_type if label_field else None

    def _check_type(label_id, label_entity_type):
        if label_entity_type and label_entity_type != endpoint_entity_type:
            raise APIQueryParamsError(
                f"label {label_id} is type '{label_entity_type}', "
                f"not valid for /{endpoint_entity_type}"
            )

    total_ids = 0

    def _budget(count):
        nonlocal total_ids
        total_ids += count
        if total_ids > MAX_RESOLVED_IDS_PER_REQUEST:
            raise APIQueryParamsError(
                f"label: filter resolved to too many entities "
                f"(max {MAX_RESOLVED_IDS_PER_REQUEST})"
            )

    # Positive labels: resolve, validate types, intersect IDs.
    if positives:
        resolved = []
        for lid in positives:
            etype, ids = resolve_label(lid)
            _budget(len(ids))
            resolved.append((lid, (etype, ids)))
        # Validate entity types against endpoint.
        for lid, (etype, _) in resolved:
            _check_type(lid, etype)
        # If any positive label is unknown / deleted, the intersection is empty.
        if any(etype is None for _, (etype, _) in resolved):
            ids = []
        else:
            sets = [set(ids) for _, (_, ids) in resolved]
            ids = sorted(set.intersection(*sets)) if sets else []
        s = s.filter(Q("terms", id=_canonicalize_entity_ids(ids)))

    # Negated labels: each becomes its own NOT clause.
    for lid in negatives:
        etype, ids = resolve_label(lid)
        if etype is None:
            # Deleted label → nothing to exclude; skip.
            continue
        _check_type(lid, etype)
        _budget(len(ids))
        s = s.filter(~Q("bool", must=Q("terms", id=_canonicalize_entity_ids(ids))))

    return s, other
