from elasticsearch_dsl import A, Q

import settings
from core.group_by.utils import get_bucket_keys, parse_group_by
from core.validate import validate_group_by
from core.preference import clean_preference
from core.utils import get_field
from countries import GLOBAL_SOUTH_COUNTRIES


def create_group_by_buckets(fields_dict, group_by_item, s, params):
    q = params.get("q")
    per_page = 500 if q else params.get("per_page")
    sort_params = params.get("sort")

    s = s.params(preference=clean_preference(group_by_item))
    field = get_field(fields_dict, group_by_item)
    validate_group_by(field)

    if field.param in ["best_open_version", "version"] or "continent" in field.param:
        return s

    group_by, known = parse_group_by(group_by_item)
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
    s.aggs.bucket(bucket_keys["default"], a)
    return s


def determine_shard_size(q):
    return 5000 if q else 3000


def get_missing(field):
    if type(field).__name__ == "RangeField" or type(field).__name__ == "BooleanField":
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
