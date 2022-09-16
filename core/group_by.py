from elasticsearch_dsl import A, Q, Search
from iso3166 import countries

import settings
from core.utils import get_display_names


def group_by_records(field, s, sort_params, known):
    group_by_field = field.alias if field.alias else field.es_sort_field()
    if type(field).__name__ == "RangeField" or type(field).__name__ == "BooleanField":
        missing = -111
    else:
        missing = "unknown"

    if sort_params:
        for key, order in sort_params.items():
            if key == "count" and not known:
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_count": order},
                    size=200,
                )
            elif key == "count" and known:
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_count": order},
                    size=200,
                )
            elif key == "key" and not known:
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_key": order},
                    size=200,
                )
            elif key == "key" and known:
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_key": order},
                    size=200,
                )
            s.aggs.bucket("groupby", a)
    elif (
        field.param in settings.EXTERNAL_ID_FIELDS
        or field.param in settings.BOOLEAN_TEXT_FIELDS
    ):
        exists = A("filter", Q("exists", field=group_by_field))
        not_exists = A("filter", ~Q("exists", field=group_by_field))
        s.aggs.bucket("exists", exists)
        s.aggs.bucket("not_exists", not_exists)
    elif known:
        a = A(
            "terms",
            field=group_by_field,
            size=200,
        )
        s.aggs.bucket("groupby", a)
    else:
        a = A(
            "terms",
            field=group_by_field,
            missing=missing,
            size=200,
        )
        s.aggs.bucket("groupby", a)
    return s


def get_group_by_results(group_by, response):
    group_by_results = []
    buckets = response.aggregations.groupby.buckets
    if group_by.endswith(".id"):
        keys = [b.key for b in buckets]
        ids_to_display_names = get_display_names(keys)
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                key_display_name = ids_to_display_names.get(b.key)
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.doc_count,
                }
            )
    elif group_by.endswith("country_code"):
        for b in buckets:
            if b.key == "unknown":
                key_display_name = "unknown"
            else:
                country = countries.get(b.key.lower())
                key_display_name = country.name if country else None
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": key_display_name,
                    "doc_count": b.doc_count,
                }
            )
    else:
        for b in buckets:
            if b.key == -111:
                key = "unknown"
            elif "key_as_string" in b:
                key = b.key_as_string
            else:
                key = b.key
            group_by_results.append(
                {"key": key, "key_display_name": key, "doc_count": b.doc_count}
            )
    return group_by_results


def get_group_by_results_external_ids(response):
    exists_count = response.aggregations.exists.doc_count
    not_exists_count = response.aggregations.not_exists.doc_count

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


def group_by_records_transform(field, parent_index, sort_params):
    index_name = get_transform_index(field, parent_index)
    s = Search(index=index_name)
    s = s.query("match_all").extra(size=200)

    if sort_params:
        for key, order in sort_params.items():
            if key == "count" and order == "desc":
                s = s.sort("-doc_count")
            elif key == "count" and order == "asc":
                s = s.sort("doc_count")
            elif key == "key" and order == "desc":
                s = s.sort("-key")
            elif key == "key" and order == "asc":
                s = s.sort("key")
    else:
        s = s.sort("-doc_count")
    return s


def get_group_by_results_transform(group_by, response):
    group_by_results = []
    if group_by.endswith(".id"):
        keys = []
        for b in response:
            if b.key:
                keys.append(b.key)
        ids_to_display_names = get_display_names(keys)
        for b in response:
            if b.key:
                key = b.key
                key_display_name = ids_to_display_names.get(b.key)
            else:
                key = "unknown"
                key_display_name = "unknown"
            group_by_results.append(
                {
                    "key": key,
                    "key_display_name": key_display_name,
                    "doc_count": b.doc_count,
                }
            )
    else:
        for b in response:
            if b.key == -111:
                key = "unknown"
            elif "key_as_string" in b:
                key = b.key_as_string
            else:
                key = b.key
            group_by_results.append(
                {"key": key, "key_display_name": key, "doc_count": b.doc_count}
            )
    return group_by_results


def is_transform(field, parent_index, filter_params):
    if filter_params:
        return False

    for transform in settings.TRANSFORMS:
        if field.param == transform["field"] and parent_index.startswith(
            transform["parent_index"]
        ):
            return True


def get_transform_index(field, parent_index):
    for transform in settings.TRANSFORMS:
        if field.param == transform["field"] and parent_index.startswith(
            transform["parent_index"]
        ):
            return transform["index_name"]
