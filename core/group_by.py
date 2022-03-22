from elasticsearch_dsl import A
from iso3166 import countries

from core.utils import get_display_names


def group_by_records(field, s, sort_params):
    group_by_field = field.alias if field.alias else field.es_sort_field()
    if type(field).__name__ == "RangeField" or type(field).__name__ == "BooleanField":
        missing = -111
    else:
        missing = "unknown"

    if sort_params:
        for key, order in sort_params.items():
            if key == "count":
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_count": order},
                    size=200,
                )
            elif key == "key":
                a = A(
                    "terms",
                    field=group_by_field,
                    missing=missing,
                    order={"_key": order},
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
