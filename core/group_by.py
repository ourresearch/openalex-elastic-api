from elasticsearch_dsl import A

from core.exceptions import APIQueryParamsError
from core.utils import get_display_names


def group_by_records(field, group_by_size, s, sort_params):
    group_by_size = validate_group_by_size(group_by_size)
    group_by_field = field.alias if field.alias else field.es_sort_field()
    if sort_params:
        for key, order in sort_params.items():
            if key == "count":
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_count": order},
                    size=group_by_size,
                )
            elif key == "key":
                a = A(
                    "terms",
                    field=group_by_field,
                    order={"_key": order},
                    size=group_by_size,
                )
            s.aggs.bucket("groupby", a)
    else:
        a = A(
            "terms",
            field=group_by_field,
            size=group_by_size,
        )
        s.aggs.bucket("groupby", a)
    return s


def validate_group_by_size(group_by_size):
    if group_by_size < 1 or group_by_size > 200:
        raise APIQueryParamsError("Group by size must be a number between 1 and 200")
    return group_by_size


def get_group_by_results(group_by, response):
    group_by_results = []
    buckets = response.aggregations.groupby.buckets
    if group_by.endswith(".id"):
        keys = [b.key for b in buckets]
        ids_to_display_names = get_display_names(keys)
        for b in buckets:
            group_by_results.append(
                {
                    "key": b.key,
                    "key_display_name": ids_to_display_names.get(b.key),
                    "doc_count": b.doc_count,
                }
            )
    else:
        for b in buckets:
            group_by_results.append(
                {"key": b.key, "key_display_name": b.key, "doc_count": b.doc_count}
            )
    return group_by_results
