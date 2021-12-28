from elasticsearch_dsl import A

from core.exceptions import APIQueryParamsError


def group_by_records(field, group_by_size, s, sort_params):
    group_by_size = validate_group_by_size(group_by_size)
    if sort_params:
        for key, order in sort_params.items():
            if key == "count":
                a = A(
                    "terms",
                    field=field.es_sort_field(),
                    order={"_count": order},
                    size=group_by_size,
                )
            elif key == "key":
                a = A(
                    "terms",
                    field=field.es_sort_field(),
                    order={"_key": order},
                    size=group_by_size,
                )
            s.aggs.bucket("groupby", a)
    else:
        a = A(
            "terms",
            field=field.es_sort_field(),
            size=group_by_size,
        )
        s.aggs.bucket("groupby", a)
    return s


def validate_group_by_size(group_by_size):
    if group_by_size < 1 or group_by_size > 200:
        raise APIQueryParamsError("Group by size must be a number between 1 and 200")
    return group_by_size
