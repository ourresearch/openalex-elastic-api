import settings
from core.group_by.buckets import (
    get_bucket_keys,
    get_default_buckets,
    buckets_to_keep,
    not_exists_bucket_count,
    exists_bucket_count,
)
from core.group_by.custom_results import (
    group_by_best_open_version,
    group_by_continent,
    group_by_version,
)
from core.group_by.utils import parse_group_by, get_all_groupby_values

from core.utils import (
    get_field,
)
from core.group_by.display_names import (
    get_key_display_name,
    get_display_name_mapping,
    requires_display_name_conversion,
)


def get_group_by_results(
    group_by,
    include_unknown,
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
        results = group_by_version(
            field, index_name, params, include_unknown, fields_dict
        )
    elif field.param == "best_open_version":
        results = group_by_best_open_version(field, index_name, params, fields_dict)
    # temp function until topics propagation done
    elif field.param in (
        "topics.domain.id",
        "topics.subdomain.id",
        "topics.field.id",
        "primary_topic.domain.id",
        "primary_topic.field.id",
        "primary_topic.subfield.id",
    ):
        results = get_topics_group_by_results(group_by, response, index_name)
    else:
        results = get_default_group_by_results(group_by, response, index_name)
    results = add_zero_values(results, include_unknown, index_name, group_by, params)

    # support new id formats so duplicates do not show up with 0 values
    if (
        field.param
        in (
            "topics.domain.id",
            "topics.subdomain.id",
            "topics.field.id",
            "primary_topic.domain.id",
            "primary_topic.field.id",
            "primary_topic.subfield.id",
            "country_code",
            "countries",
            "language",
            "sustainable_development_goals.id",
            "locations.source.type",
            "primary_location.source.type",
        )
        or (field.param == "type" and "works" in index_name)
        or (field.param == "type" and "sources" in index_name)
    ):
        results = [result for result in results if "openalex.org" in result["key"]]
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


def get_default_group_by_results(group_by, response, index_name):
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
        result = get_result(b, key_display_names, group_by, index_name)
        if result:
            group_by_results.append(result)

    return group_by_results


def get_topics_group_by_results(group_by, response, index_name):
    group_by_results = []
    buckets = get_default_buckets(group_by, response)
    buckets = buckets_to_keep(buckets, group_by)

    if requires_display_name_conversion(group_by):
        keys = [b.key for b in buckets]
        key_display_names = get_display_name_mapping(keys, group_by)
    else:
        key_display_names = {}

    for b in buckets:
        result = get_result(b, key_display_names, group_by, index_name)
        if result:
            group_by_results.append(result)

    # format single integer keys as URLs
    entity = f"{group_by.split('.')[1]}s"
    for group_by_result in group_by_results:
        if "openalex.org" not in group_by_result["key"]:
            group_by_result[
                "key"
            ] = f"https://openalex.org/{entity}/{group_by_result['key']}"

    # merge the duplicate ids together and sum the doc_counts
    for group_by_result in group_by_results:
        if (
            group_by_result["key"] in [item["key"] for item in group_by_results]
            and group_by_result["key_display_name"]
        ):
            group_by_result["doc_count"] = sum(
                [
                    item["doc_count"]
                    for item in group_by_results
                    if item["key"] == group_by_result["key"]
                ]
            )
            group_by_results = [
                item
                for item in group_by_results
                if item["key"] != group_by_result["key"]
            ]
            group_by_results.append(group_by_result)

    return group_by_results


def get_result(b, key_display_names, group_by, index_name):
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

    if "cited_by_percentile_year" in group_by:
        # format as one decimal place
        b.key = str(round(b.key, 1))

    key = format_key(b.key, group_by, index_name)
    return {"key": key, "key_display_name": key_display_name, "doc_count": doc_count}


def add_zero_values(results, include_unknown, index_name, field, params):
    ignore_values = set([str(item["key"]) for item in results])
    if not include_unknown:
        ignore_values.update(["unknown", "-111"])
    possible_buckets = get_all_groupby_values(
        entity=index_name.split("-")[0], field=field
    )
    for bucket in possible_buckets:
        if (
            bucket["key"] not in ignore_values
            and not bucket["key"].startswith("http://metadata.un.org")
            and len(results) < params["per_page"]
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


def format_key(key, group_by, index_name):
    id_prefix = "https://openalex.org"
    if group_by.endswith("country_code") or group_by.endswith("countries"):
        formatted_key = f"{id_prefix}/countries/{key.upper()}"
    elif group_by == "language":
        formatted_key = f"{id_prefix}/languages/{key}"
    elif group_by == "type" and "works" in index_name:
        formatted_key = f"{id_prefix}/work-types/{key}"
    elif group_by == "sustainable_development_goals.id":
        sdg_number = key.split("/")[-1]
        formatted_key = f"{id_prefix}/sdgs/{sdg_number}"
    elif (
        group_by == "locations.source.type"
        or group_by == "primary_location.source.type"
        or (group_by == "type" and "sources" in index_name)
    ):
        key = key.replace(" ", "%20")
        formatted_key = f"{id_prefix}/source-types/{key}"
    else:
        formatted_key = key
    return formatted_key
