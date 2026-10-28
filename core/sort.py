from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.group_by.buckets import parse_metric_sort_key
from core.utils import get_field
from core.preference import clean_preference


def get_sort_fields(fields_dict, group_by, sort_params):
    sort_fields = []
    for key, value in sort_params.items():
        # group by (yes/no groups sort like any others since oxjob #1859)
        if (
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
        refusal = sort_refusal(key, field)
        if refusal:
            raise APIQueryParamsError(refusal)
        if value == "asc":
            sort_fields.append(field.es_sort_field())
        elif value == "desc":
            sort_fields.append(f"-{field.es_sort_field()}")
    return sort_fields


# Filters that hold no value to sort by, and what people sorting by them mean (oxjob #1900).
# Most sort=cited_by and sort=cites requests come with a search: they want the most cited first.
SORT_INSTEAD = {
    "cited_by": "cited_by_count",
    "cites": "cited_by_count",
}


def sort_refusal(key, field):
    """Why `sort=<key>` can't run, or None when it can (oxjob #1900).

    The same rule as the sort capability /properties publishes (core.properties._derive_actions):
    a filter column whose Field is sortable. Before, any other key reached Elasticsearch and
    came back as an HTML 500 ("No mapping found for [cited_by] in order to sort on")."""
    if "filter" not in field.actions:
        if "search" in field.actions:
            return (
                f"Cannot sort by {key}: it is a search filter. To put the best matches "
                f"first, use sort=relevance_score:desc."
            )
        return f"Cannot sort by {key}: it is not a value the results have."
    if getattr(field, "sortable", True):
        return None
    if getattr(field, "target_entity", None):  # JoinField (#1526)
        return f"Cannot sort by {key}: it is a filter on a related entity, looked up at query time."
    instead = SORT_INSTEAD.get(key)
    if instead:
        return (
            f"Cannot sort by {key}: it filters by a citation link to one work, so it has no "
            f"value to sort by. To sort by number of citations, use sort={instead}:desc."
        )
    return f"Cannot sort by {key}: it is a filter only, with no stored value to sort by."


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
