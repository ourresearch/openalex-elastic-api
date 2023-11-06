from elasticsearch_dsl import A, Q, AttrDict

import settings
from core.cursor import decode_group_by_cursor
from core.group_by.utils import get_bucket_keys, parse_group_by
from core.validate import validate_group_by
from core.preference import clean_preference
from core.utils import get_field
from countries import GLOBAL_SOUTH_COUNTRIES


"""
Bucket creation.
"""


def create_group_by_buckets(fields_dict, group_by, known, s, params):
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
            known,
            missing,
            per_page,
            s,
            shard_size,
            sort_params,
        )
    elif "is_global_south" in field.param:
        create_global_south_group_by_buckets(bucket_keys, group_by_field, s)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
        create_boolean_group_by_buckets(bucket_keys, group_by_field, s)
    elif cursor:
        if cursor and cursor != "*":
            after_key = decode_group_by_cursor(cursor)
        else:
            after_key = None
        create_pagination_group_by_buckets(
            bucket_keys, group_by_field, known, missing, params, s, after_key
        )
    else:
        create_default_group_by_buckets(
            bucket_keys, group_by_field, known, missing, per_page, s, shard_size
        )

    return s


def create_sorted_group_by_buckets(
    bucket_keys, group_by_field, known, missing, per_page, s, shard_size, sort_params
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
            if not known:
                a.missing = missing
            if "cited_by_percentile_year" in group_by_field:
                a.format = "0.0"
            s.aggs.bucket(bucket_keys["default"], a)
    return s


def create_global_south_group_by_buckets(bucket_keys, group_by_field, s):
    country_codes = [c["country_code"] for c in GLOBAL_SOUTH_COUNTRIES]
    exists = A("filter", Q("terms", **{group_by_field: country_codes}))
    not_exists = A("filter", ~Q("terms", **{group_by_field: country_codes}))
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
    bucket_keys, group_by_field, known, missing, params, s, after_key
):
    sources = [{"sub_key": {"terms": {"field": group_by_field}}}]

    composite_agg = A("composite", sources=sources, size=params["per_page"])

    if after_key:
        composite_agg.after = after_key

    # handle missing value
    if known and missing is not None:
        s = s.filter("bool", must=[{"exists": {"field": group_by_field.es_field()}}])
    s.aggs.bucket(bucket_keys["default"], composite_agg)
    return s


def create_default_group_by_buckets(
    bucket_keys, group_by_field, known, missing, per_page, s, shard_size
):
    a = A(
        "terms",
        field=group_by_field,
        size=per_page,
        shard_size=shard_size,
    )
    if not known:
        a.missing = missing
    if "cited_by_percentile_year" in group_by_field:
        a.format = "0.0"
    s.aggs.bucket(bucket_keys["default"], a)
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
