from elasticsearch_dsl import A, Q, AttrDict
from flask import current_app as app


import settings
from core.cursor import decode_group_by_cursor
from core.exceptions import APIQueryParamsError
from core.group_by.utils import get_bucket_keys
from core.validate import validate_group_by
from core.preference import clean_preference
from core.utils import get_field
from country_list import GLOBAL_SOUTH_COUNTRIES


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

    if field.param in ["best_open_version", "version"] or "continent" in field.param:
        return s

    group_by_field = field.alias if field.alias else field.es_sort_field()

    bucket_keys = get_bucket_keys(group_by)

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
    elif "is_global_south" in field.param:
        create_global_south_group_by_buckets(bucket_keys, group_by_field, s)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
        create_boolean_group_by_buckets(bucket_keys, group_by_field, s)
    elif field.param == "mag_only":
        create_mag_only_group_by_buckets(bucket_keys, s)
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
    for key, order in sort_params.items():
        if key in ["count", "key"]:
            order_key = f"_{key}"
            a = A(
                "terms",
                field=group_by_field,
                order={order_key: order},
                size=per_page,
                shard_size=shard_size,
            )
            if include_unknown:
                a.missing = missing
            if "cited_by_percentile_year" in group_by_field:
                a.format = "0.0"
            s.aggs.bucket(bucket_keys["default"], a)
            continue

        # Metric-aggregate sort (oxjob #389): order the buckets by a metric
        # sub-aggregation (mean/sum/min/max of a numeric field). ES computes the
        # sub-agg per bucket and orders the terms agg by its path natively.
        metric_field, metric = parse_metric_sort_key(key)
        if metric_field and metric:
            metric_es_field = resolve_metric_es_field(fields_dict, metric_field)
            a = A(
                "terms",
                field=group_by_field,
                order={GROUP_BY_METRIC_AGG_NAME: order},
                size=per_page,
                shard_size=shard_size,
            )
            if include_unknown:
                a.missing = missing
            if "cited_by_percentile_year" in group_by_field:
                a.format = "0.0"
            # Attach the metric sub-agg the terms agg orders by; its value is also
            # surfaced per group (core.group_by.results.get_result reads it back).
            a.metric(
                GROUP_BY_METRIC_AGG_NAME,
                GROUP_BY_METRICS[metric],
                field=metric_es_field,
            )
            s.aggs.bucket(bucket_keys["default"], a)
            continue
    return s


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


def create_global_south_group_by_buckets(bucket_keys, group_by_field, s):
    country_codes = [c["country_code"] for c in GLOBAL_SOUTH_COUNTRIES]
    exists = A("filter", Q("terms", **{group_by_field: country_codes}))
    not_exists = A("filter", ~Q("terms", **{group_by_field: country_codes}))
    s.aggs.bucket(bucket_keys["exists"], exists)
    s.aggs.bucket(bucket_keys["not_exists"], not_exists)
    return s


def create_mag_only_group_by_buckets(bucket_keys, s):
    exists = A(
        "filter",
        (
            Q("exists", field="ids.mag")
            & ~Q("exists", field="ids.pmid")
            & ~Q("exists", field="ids.pmcid")
            & ~Q("exists", field="ids.doi")
            & ~Q("exists", field="ids.arxiv")
        ),
    )
    not_exists = A(
        "filter",
        (
            Q("exists", field="ids.pmid")
            | Q("exists", field="ids.pmcid")
            | Q("exists", field="ids.doi")
            | Q("exists", field="ids.arxiv")
        ),
    )
    s.aggs.bucket(bucket_keys["exists"], exists)
    s.aggs.bucket(bucket_keys["not_exists"], not_exists)
    return s


def create_boolean_group_by_buckets(bucket_keys, group_by_field, s):
    exists = A("filter", Q("exists", field=group_by_field))
    not_exists = A("filter", ~Q("exists", field=group_by_field))
    s.aggs.bucket(bucket_keys["exists"], exists)
    s.aggs.bucket(bucket_keys["not_exists"], not_exists)
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
    if "cited_by_percentile_year" in group_by_field:
        a.format = "0.0"
    s.aggs.bucket(bucket_keys["default"], a)
    return s


def _reject_unsupported_nested_field(field):
    """The exotic single-dim group_by shapes (boolean exists/not-exists pairs,
    external-id booleans, global-south, mag_only, continent, version,
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
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
        or type(field).__name__ == "BooleanField"
        or "is_global_south" in field.param
        or field.param == "mag_only"
        or "continent" in field.param
        or field.param in ("version", "best_open_version")
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
    shard_size = determine_shard_size(q)

    preference_seed = ",".join(group_by for group_by, _ in dimensions)
    s = s.params(preference=clean_preference(preference_seed))

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
        if "cited_by_percentile_year" in group_by_field:
            a.format = "0.0"

        parent = parent.bucket(bucket_key, a)
    return s


def determine_shard_size(q):
    return 5000 if q else 3000


def get_missing(field):
    if (
        type(field).__name__ == "RangeField"
        or type(field).__name__ == "BooleanField"
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
        s = s.filter("term", **{"locations.source.type": "repository"})
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


def get_bucket_doc_count(group_by, response, bucket_key):
    bucket_keys = get_bucket_keys(group_by)
    return response.aggregations[bucket_keys[bucket_key]].doc_count


def exists_bucket_count(group_by, response):
    return get_bucket_doc_count(group_by, response, "exists")


def not_exists_bucket_count(group_by, response):
    return get_bucket_doc_count(group_by, response, "not_exists")


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
