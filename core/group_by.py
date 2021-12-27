from elasticsearch_dsl import A


def group_by_records(field, group_by_size, s):
    a = A(
        "terms",
        field=field.es_sort_field(),
        # order={"_term": "desc"},
        size=group_by_size,
    )
    s.aggs.bucket("groupby", a)
    return s
