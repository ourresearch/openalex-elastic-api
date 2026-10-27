from elasticsearch_dsl import A, AttrDict
from flask import current_app as app


from core.cursor import decode_group_by_cursor
from core.exceptions import APIQueryParamsError
from core.group_by.utils import get_bucket_keys, is_boolean_field, is_works_version_group_by
from core.validate import validate_group_by
from core.preference import clean_preference
from core.utils import get_field


# Multi-dimensional (nested) group_by — oxjob #387. ES nests terms aggs natively
# (no mapping change). We cap the depth: each level multiplies bucket cardinality,
# so deep nesting is an ES-load footgun.
MAX_GROUP_BY_DIMENSIONS = 3


# Sort group_by buckets by a metric SUB-AGGREGATION — oxjob #389 (old corpus row
# L18, e.g. funders ranked by mean(cited_by_count) of their works). ES computes a
# metric sub-agg on each bucket and orders the terms agg by its path natively (no
# mapping change). The URL/sort surface is a dotted pseudo-field
# `sort=<numeric_field>.<metric>:desc` (e.g. `cited_by_count.mean:desc`).
#
# Maps our public metric names -> ES metric agg types. `mean` -> ES `avg`.
GROUP_BY_METRICS = {
    "mean": "avg",
    "sum": "sum",
    "min": "min",
    "max": "max",
}

# The sub-agg name we attach to each bucket and order by. Also the prefix of the
# surfaced response key (`<metric>_<field>`, e.g. `mean_cited_by_count`).
GROUP_BY_METRIC_AGG_NAME = "group_by_metric"


def parse_metric_sort_key(key):
    """Split a dotted metric sort key `<field>.<metric>` into `(field, metric)`,
    or return `(None, None)` when `key` is not a metric-aggregate sort key.

    `metric` must be one of GROUP_BY_METRICS (mean/sum/min/max). The field part
    may itself contain dots (e.g. `apc_paid.value_usd.mean`) — only the LAST
    dotted segment is the metric, so we rsplit once. Plain bucket-order keys
    (`count`/`key`) and non-metric sort columns return `(None, None)`.
    """
    if not isinstance(key, str) or "." not in key:
        return None, None
    field_part, _, metric = key.rpartition(".")
    if metric in GROUP_BY_METRICS and field_part:
        return field_part, metric
    return None, None


"""
Bucket creation.
"""


def create_group_by_buckets(fields_dict, group_by, include_unknown, s, params):
    cursor = params.get("cursor")
    q = params.get("q")
    per_page = 500 if q else params.get("per_page")
    sort_params = params.get("sort")

    s = s.params(preference=clean_preference(group_by))
    field = get_field(fields_dict, group_by)
    validate_group_by(field, params)

    if (
        field.param == "best_open_version"
        or is_works_version_group_by(field)
        or "continent" in field.param
    ):
        return s

    bucket_keys = get_bucket_keys(group_by)
    if is_boolean_field(field):
        return create_boolean_group_by_buckets(
            field, bucket_keys, include_unknown, s, sort_params, fields_dict
        )

    group_by_field = field.alias if field.alias else field.es_sort_field()

    missing = get_missing(field)
    shard_size = determine_shard_size(q)

    s = filter_by_repository_or_journal(field, s)

    if sort_params:
        create_sorted_group_by_buckets(
            bucket_keys,
            group_by_field,
            include_unknown,
            missing,
            per_page,
            s,
            shard_size,
            sort_params,
            fields_dict,
        )
    elif cursor:
        if cursor and cursor != "*":
            after_key = decode_group_by_cursor(cursor)
        else:
            after_key = None
        create_pagination_group_by_buckets(
            bucket_keys, group_by_field, include_unknown, missing, params, s, after_key
        )
    else:
        create_default_group_by_buckets(
            bucket_keys,
            group_by_field,
            include_unknown,
            missing,
            per_page,
            s,
            shard_size,
        )

    return s


def create_sorted_group_by_buckets(
    bucket_keys,
    group_by_field,
    include_unknown,
    missing,
    per_page,
    s,
    shard_size,
    sort_params,
    fields_dict=None,
):
    for key, direction in sort_params.items():
        spec = _group_order(fields_dict, key, direction)
        if spec is None:
            continue
        a = A("terms", field=group_by_field, size=per_page, shard_size=shard_size)
        if include_unknown:
            a.missing = missing
        _apply_field_hints(a, group_by_field)
        _apply_group_order(a, spec)
        s.aggs.bucket(bucket_keys["default"], a)
    return s


def last_group_sort(sort_params):
    """The (key, direction) that orders groups: the last `count`, `key` or metric
    sort key, as on a nested group_by (oxjob #1513). None when none orders groups."""
    last = None
    for key, direction in (sort_params or {}).items():
        if key in ("count", "key") or parse_metric_sort_key(key)[1]:
            last = (key, direction)
    return last


def _group_order(fields_dict, key, direction):
    """How one sort key orders groups: `count` / `key`, or a metric
    (`cited_by_count.mean`, oxjob #389). Returns (terms order, metric sub-agg as
    (es agg, es field) or None), or None for a key that doesn't order groups."""
    if key in ("count", "key"):
        return {f"_{key}": direction}, None
    metric_field, metric = parse_metric_sort_key(key)
    if metric_field and metric:
        es_field = resolve_metric_es_field(fields_dict, metric_field)
        return {GROUP_BY_METRIC_AGG_NAME: direction}, (GROUP_BY_METRICS[metric], es_field)
    return None


def _apply_group_order(a, spec):
    """Order a terms agg by `spec` (from `_group_order`). ES orders by the metric
    sub-agg natively; get_result reads its value back per group."""
    order, metric = spec
    a.order = order
    if metric:
        a.metric(GROUP_BY_METRIC_AGG_NAME, metric[0], field=metric[1])


def resolve_metric_es_field(fields_dict, metric_field):
    """Resolve the metric sort key's field part to its ES field path, rejecting
    non-numeric (non-RangeField) columns with a clear 400. A metric sub-agg
    (avg/sum/min/max) only makes sense over a numeric field; ordering by a metric
    of a keyword/date field is a user error, not a silent empty result."""
    if not fields_dict or metric_field not in fields_dict:
        raise APIQueryParamsError(
            f"Invalid sort field '{metric_field}'. Metric-aggregate group sort "
            f"requires a numeric field, e.g. cited_by_count.mean:desc."
        )
    field = fields_dict[metric_field]
    if type(field).__name__ != "RangeField":
        raise APIQueryParamsError(
            f"Cannot compute a metric aggregate over non-numeric field "
            f"'{metric_field}'. Metric-aggregate group sort "
            f"(mean/sum/min/max) requires a numeric field."
        )
    return field.es_field()


def create_boolean_group_by_buckets(
    field, bucket_keys, include_unknown, s, sort_params, fields_dict
):
    """A yes/no group_by counts what its own filter matches: group "true" = the works
    `filter=<field>:true` returns, "false" = those `<field>:false` returns, and with
    include_unknown, "unknown" = works neither matches (ES's other bucket). It used to
    run a terms agg on the raw field or an `exists` on it, which disagreed with the
    filter: every work carries `has_abstract`, so group_by put all 328M under true
    while the filter found 148.7M without one; columns with no ES field of their own
    (has_oa_accepted_or_published_version) came back empty (oxjob #1859)."""
    a = A(
        "filters",
        filters={"true": field.query_for("true"), "false": field.query_for("false")},
    )
    if include_unknown:
        a.other_bucket_key = "unknown"
    # a metric sort (`cited_by_count.mean:desc`) returns its value per group;
    # get_boolean_group_by_results orders the groups
    order = last_group_sort(sort_params)
    spec = _group_order(fields_dict, *order) if order else None
    if spec and spec[1]:
        a.metric(GROUP_BY_METRIC_AGG_NAME, spec[1][0], field=spec[1][1])
    s.aggs.bucket(bucket_keys["default"], a)
    return s


def create_pagination_group_by_buckets(
    bucket_keys, group_by_field, include_unknown, missing, params, s, after_key
):
    terms_source = {"field": group_by_field}
    if include_unknown and missing is not None:
        terms_source["missing_bucket"] = True
    sources = [{"sub_key": {"terms": terms_source}}]

    composite_agg = A("composite", sources=sources, size=params["per_page"])

    if after_key:
        composite_agg.after = after_key

    try:
        if not include_unknown and missing is not None:
            s = s.filter(
                "bool", must=[{"exists": {"field": group_by_field.es_field()}}]
            )
    except AttributeError:
        app.logger.warn(f"No field available for {group_by_field}.es_field()")
    s.aggs.bucket(bucket_keys["default"], composite_agg)
    return s


def create_default_group_by_buckets(
    bucket_keys, group_by_field, include_unknown, missing, per_page, s, shard_size
):
    a = A(
        "terms",
        field=group_by_field,
        size=per_page,
        shard_size=shard_size,
    )
    if include_unknown:
        a.missing = missing
    _apply_field_hints(a, group_by_field)
    s.aggs.bucket(bucket_keys["default"], a)
    return s


# `referenced_works` and `related_works` carry no eager global ordinals, so a plain
# terms agg builds them on every request: about 10 s even on 3,827 works (#1512),
# past the 7 s client timeout, so `group_by=cites` answered HTTP 500 (oxjob #1513).
# `map` reads the matching works' values directly: 0.4 s, the same buckets.
# shortcut: map's cost grows with the matching set; on tens of millions of works
# the search's 5 s soft timeout (execute_search) cuts it off. If broad sets get
# common, eager global ordinals on the mapping are the fix (Casey owns mappings).
_MAP_HINT_FIELDS = ("referenced_works", "related_works")


def _apply_field_hints(a, group_by_field):
    if "cited_by_percentile_year" in group_by_field:
        a.format = "0.0"
    if group_by_field in _MAP_HINT_FIELDS:
        a.execution_hint = "map"


def _reject_unsupported_nested_field(field):
    """The exotic single-dim group_by shapes (yes/no columns, continent, version,
    best_open_version) use bespoke bucket builders + result paths that don't
    nest. Multi-dim group_by supports the plain `terms`-agg fields only — reject
    the rest with a clear 400 rather than silently producing wrong buckets."""
    # Topic-hierarchy id fields carry bare-integer bucket keys that a dedicated
    # single-dim path (results.get_topics_group_by_results) rewrites to URLs and
    # de-dupes; that logic doesn't nest. Reject for now (oxjob #387 scope; can be
    # added later). `primary_topic.id` itself is a normal URL-keyed field and is
    # fully supported.
    topic_hierarchy_fields = (
        "topics.domain.id",
        "topics.subdomain.id",
        "topics.field.id",
        "primary_topic.domain.id",
        "primary_topic.field.id",
        "primary_topic.subfield.id",
    )
    if (
        is_boolean_field(field)
        or "continent" in field.param
        or field.param == "best_open_version"
        or is_works_version_group_by(field)
        or field.param in topic_hierarchy_fields
    ):
        raise APIQueryParamsError(
            f"Field '{field.param}' is not supported in a multi-dimensional "
            f"group_by. Combine plain group-able fields instead."
        )


def create_nested_group_by_buckets(fields_dict, dimensions, s, params):
    """Build a NESTED chain of terms aggregations — one level per dimension,
    outermost first — so the response is a cross-product (e.g. years within each
    topic). oxjob #387. Single-dim grouping is untouched; this path runs only
    when `group_by=a,b[,c]`."""
    if len(dimensions) > MAX_GROUP_BY_DIMENSIONS:
        raise APIQueryParamsError(
            f"group_by supports at most {MAX_GROUP_BY_DIMENSIONS} dimensions; "
            f"got {len(dimensions)}."
        )
    if params.get("cursor"):
        raise APIQueryParamsError(
            "Cursor pagination is not supported with multi-dimensional group_by."
        )

    q = params.get("q")
    per_page = 500 if q else params.get("per_page")
    shard_size = determine_shard_size(q, nested=True)

    preference_seed = ",".join(group_by for group_by, _ in dimensions)
    s = s.params(preference=clean_preference(preference_seed))
    # every level takes the sort's order, as a single-field group does (the last
    # key that orders groups wins); it used to be ignored (oxjob #1513)
    specs = [spec for key, direction in (params.get("sort") or {}).items()
             if (spec := _group_order(fields_dict, key, direction))]

    parent = s.aggs
    for group_by, include_unknown in dimensions:
        field = get_field(fields_dict, group_by)
        validate_group_by(field, params)
        _reject_unsupported_nested_field(field)
        s = filter_by_repository_or_journal(field, s)

        group_by_field = field.alias if field.alias else field.es_sort_field()
        bucket_key = get_bucket_keys(group_by)["default"]

        a = A("terms", field=group_by_field, size=per_page, shard_size=shard_size)
        if include_unknown:
            a.missing = get_missing(field)
        _apply_field_hints(a, group_by_field)
        if specs:
            _apply_group_order(a, specs[-1])

        parent = parent.bucket(bucket_key, a)
    return s


def determine_shard_size(q, nested=False):
    """How many top keys each shard sends for a terms group list. Works sit on 72
    shards, so an author with ~100 works has one or two per shard and ties there
    with thousands of collaboration-paper authors; a short shard list drops them
    on some shards and the author is undercounted or missing. On 20 big
    institutions' 2023 works plus Medicine 2024, the top 10 authors had 85 wrong
    counts and 37 wrong people at 3,000 keys, 9 and 3 at 10,000, 2 and 0 at
    20,000; top 200: 253 wrong people at 10,000, 19 at 20,000; ES time ~0.4 s,
    ~0.55 s, ~0.6 s (oxjob #1513, 2026-10-27). Only high-cardinality fields pay:
    a field with fewer keys per shard sends what it has. Nested group_bys keep
    3,000: there the size multiplies across levels."""
    if q:
        return 5000
    return 3000 if nested else SINGLE_LIST_SHARD_SIZE


SINGLE_LIST_SHARD_SIZE = 20_000


def get_missing(field):
    if (
        type(field).__name__ == "RangeField"
        or field.param == "ids.crossref"
    ):
        missing = -111
    else:
        missing = "unknown"
    return missing


def filter_by_repository_or_journal(field, s):
    if (
        field.param == "repository"
        or field.param == "locations.source.host_institution_lineage"
    ):
        s = s.filter("term", **{"locations_full.source.type": "repository"})
    if field.param == "journal":
        s = s.filter("term", **{"primary_location.source.type": "journal"})
    return s


"""
Bucket retrieval.
"""


def get_default_buckets(group_by, response):
    bucket_keys = get_bucket_keys(group_by)
    buckets = response.aggregations[bucket_keys["default"]].buckets
    buckets = transform_paginated_buckets(buckets)
    return buckets


def transform_paginated_buckets(buckets):
    """
    Paginated buckets (composite) have a different structure than non-paginated buckets.
    Convert the paginated buckets to the same structure as non-paginated buckets.
    """
    for b in buckets:
        if isinstance(b.key, AttrDict):
            b.key = b.key["sub_key"]
        if b.key is None:
            b.key = "unknown"
    return buckets


def buckets_to_keep(buckets, group_by):
    if group_by.endswith("host_institution_lineage"):
        buckets = keep_institution_buckets(buckets)
    elif group_by.endswith("publisher_lineage"):
        buckets = keep_publisher_buckets(buckets)
    return buckets


def filter_buckets_by_key_start(buckets, key_prefix):
    return [
        b
        for b in buckets
        if b["key"] and (b["key"].startswith(key_prefix) or b["key"] == "unknown")
    ]


def keep_institution_buckets(buckets):
    return filter_buckets_by_key_start(buckets, "https://openalex.org/I")


def keep_publisher_buckets(buckets):
    return filter_buckets_by_key_start(buckets, "https://openalex.org/P")


def create_apc_sum(params, index_name, s):
    display_apc_sum = params.get("apc_sum") and params.get("apc_sum").lower() == "true"
    if display_apc_sum and index_name.startswith("sources"):
        a = A("sum", field="apc_usd")
        s.aggs.bucket("apc_list_sum_usd", a)
    elif display_apc_sum and index_name.startswith("works"):
        a = A("sum", field="apc_list.value_usd")
        s.aggs.bucket("apc_list_sum_usd", a)
        s.aggs.bucket(
            "filtered_apc_paid_sum",
            "filter",
            filter={"terms": {"open_access.oa_status": ["gold", "hybrid"]}},
            aggs={"apc_paid_sum_usd": A("sum", field="apc_paid.value_usd")},
        )
    return s


def create_cited_by_count_sum(params, s):
    display_cited_by_count_sum = (
        params.get("cited_by_count_sum")
        and params.get("cited_by_count_sum").lower() == "true"
    )
    if display_cited_by_count_sum:
        a = A("sum", field="cited_by_count")
        s.aggs.bucket("cited_by_count_sum", a)
    return s


def add_meta_sums(params, index_name, s):
    s = create_apc_sum(params, index_name, s)
    s = create_cited_by_count_sum(params, s)
    return s
