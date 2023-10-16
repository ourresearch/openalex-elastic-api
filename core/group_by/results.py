import settings
from core.group_by.buckets import (
    get_bucket_keys,
    get_default_buckets,
    buckets_to_keep,
    not_exists_bucket_count,
    exists_bucket_count,
)
from core.group_by.custom_results import group_by_best_open_version, group_by_continent, group_by_version
from core.group_by.utils import parse_group_by

from core.utils import (
    get_field,
)
from group_by.utils import get_all_groupby_values
from core.group_by.display_names import (
    get_key_display_name,
    get_display_name_mapping,
    requires_display_name_conversion,
)


def get_group_by_results(
    group_by,
    known,
    params,
    index_name,
    fields_dict,
    response,
):
    """
    Top level function for getting boolean, custom, or default group by results.
    """
    field = get_field(fields_dict, group_by)
    if is_boolean_group_by(group_by):
        return get_boolean_group_by_results(response, group_by)
    elif "continent" in field.param:
        results = group_by_continent(field, index_name, params, fields_dict)
    elif field.param == "version":
        results = group_by_version(field, index_name, params, fields_dict)
    elif field.param == "best_open_version":
        results = group_by_best_open_version(field, index_name, params, fields_dict)
    else:
        results = get_default_group_by_results(group_by, response)
    results = add_zero_values(results, known, index_name, group_by)
    return results


def is_boolean_group_by(group_by):
    return (
        group_by in settings.EXTERNAL_ID_FIELDS
        or group_by in settings.BOOLEAN_TEXT_FIELDS
        or "is_global_south" in group_by
    )


def get_boolean_group_by_results(response, group_by):
    exists_count = exists_bucket_count(group_by, response)
    not_exists_count = not_exists_bucket_count(group_by, response)

    group_by_results = [
        {
            "key": "true",
            "key_display_name": "true",
            "doc_count": exists_count,
        },
        {
            "key": "false",
            "key_display_name": "false",
            "doc_count": not_exists_count,
        },
    ]
    return group_by_results


def get_default_group_by_results(group_by, response):
    """
    Default group by results.
    """
    group_by_results = []
    buckets = get_default_buckets(group_by, response)
    buckets = buckets_to_keep(buckets, group_by)

    if requires_display_name_conversion(group_by):
        keys = [b.key for b in buckets]
        key_display_names = get_display_name_mapping(keys, group_by)
    else:
        key_display_names = {}

    for b in buckets:
        result = get_result(b, key_display_names, group_by)
        if result:
            group_by_results.append(result)

    return group_by_results


def get_result(b, key_display_names, group_by):
    if group_by in ["authorships.author.id", "author.id"]:
        if not key_display_names or not key_display_names.get(b.key):
            return None

    if b.key == "unknown":
        key_display_name = "unknown"
    elif key_display_names:
        key_display_name = key_display_names.get(b.key)
    else:
        key_display_name = get_key_display_name(b, group_by)

    doc_count = b.inner.doc_count if "inner" in b else b.doc_count

    return {"key": b.key, "key_display_name": key_display_name, "doc_count": doc_count}


def add_zero_values(results, known, index_name, field):
    ignore_values = set([item["key"] for item in results])
    if known:
        ignore_values.update(["unknown", "-111"])
    possible_buckets = get_all_groupby_values(
        entity=index_name.split("-")[0], field=field
    )
    for bucket in possible_buckets:
        if bucket["key"] not in ignore_values and not bucket["key"].startswith(
            "http://metadata.un.org"
        ):
            results.append(
                {
                    "key": bucket["key"],
                    "key_display_name": bucket["key_display_name"],
                    "doc_count": 0,
                }
            )
    return results


def calculate_group_by_count(params, response):
    group_by, _ = parse_group_by(params["group_by"])
    bucket_keys = get_bucket_keys(group_by)
    if (
        group_by in settings.EXTERNAL_ID_FIELDS
        or group_by in settings.BOOLEAN_TEXT_FIELDS
    ):
        return 2
    if "is_global_south" in group_by:
        return 2
    if any(
        keyword in group_by for keyword in ["continent", "version", "best_open_version"]
    ):
        return 3
    return len(response.aggregations[bucket_keys["default"]].buckets)
