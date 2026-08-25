from elasticsearch_dsl import Q

import settings
from core.exceptions import APIQueryParamsError
from core.group_by.buckets import parse_metric_sort_key
from core.utils import get_field
from core.preference import clean_preference


def get_sort_fields(fields_dict, group_by, sort_params):
    sort_fields = []
    for key, value in sort_params.items():
        # group by
        if (
            group_by in settings.EXTERNAL_ID_FIELDS
            or group_by in settings.BOOLEAN_TEXT_FIELDS
        ):
            raise APIQueryParamsError(
                "Cannot sort when grouping by external ID boolean field."
            )
        elif (
            group_by
            and (key == "key" and (value == "desc" or value == "asc"))
            or group_by
            and (key == "count" and (value == "desc" or value == "asc"))
        ):
            return sort_fields
        elif group_by and parse_metric_sort_key(key)[0] and value in ("asc", "desc"):
            # Metric-aggregate group sort (oxjob #389): e.g.
            # `group_by=primary_funder.id&sort=cited_by_count.mean:desc`. The
            # ordering is applied on the terms agg itself (create_sorted_group_by_buckets
            # builds the metric sub-agg + `order`), not on the entity rows — so,
            # like key/count, return no row-level sort fields here.
            return sort_fields
        elif group_by:
            raise APIQueryParamsError(
                "Valid sort params with group by are: key, count, or "
                "<numeric_field>.<metric> (mean/sum/min/max), e.g. "
                "cited_by_count.mean:desc"
            )

        # relevance key
        if key == "relevance_score" and value == "desc":
            sort_fields.append("_score")
            continue
        elif key == "relevance_score" and value == "asc":
            raise APIQueryParamsError(
                "Sorting relevance score ascending is not allowed."
            )

        # override publication_year into publication_date
        if key == "publication_year":
            key = "publication_date"

        # all others
        field = get_field(fields_dict, key)
        if value == "asc":
            sort_fields.append(field.es_sort_field())
        elif value == "desc":
            sort_fields.append(f"-{field.es_sort_field()}")
    return sort_fields


WORKS_TIE_BREAK_SORT = ["-publication_date", "id"]


def with_tie_break(sort_fields, default_sort, index_name):
    """Append a deterministic tie-break tail to an explicit sort (oxjob #879).

    Explicit sorts (e.g. ?sort=cited_by_count:desc) used to end at the user's
    fields, so tied rows came back in arbitrary ES internal order (shard +
    Lucene doc id), which can change on segment merge/reindex. Mirror the
    cursor path (sort_with_cursor), which already appends default_sort, but
    use a more legible tail for works: newest publication first, then id.

    Fields already in the user's sort are not re-appended; a sort that already
    contains the unique `id` key is left untouched (already deterministic).
    """
    if not sort_fields:
        return sort_fields
    seen = {f[1:] if f.startswith("-") else f for f in sort_fields}
    if "id" in seen:
        return sort_fields
    tail = WORKS_TIE_BREAK_SORT if index_name.startswith("works") else default_sort
    return sort_fields + [
        f for f in tail if (f[1:] if f.startswith("-") else f) not in seen
    ]


def sort_with_cursor(default_sort, fields_dict, group_by, s, sort_params):
    sort_fields = get_sort_fields(fields_dict, group_by, sort_params)
    sort_fields_with_default = sort_fields + default_sort
    s = s.sort(*sort_fields_with_default)
    return s


def sort_with_sample(s, seed):
    if seed:
        random_query = Q(
            "function_score",
            functions={"random_score": {"seed": seed, "field": "_seq_no"}},
        )
        s = s.params(preference=clean_preference(seed))
    else:
        random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query)
    return s
