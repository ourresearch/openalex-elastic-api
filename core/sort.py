from elasticsearch_dsl import Q

import settings
from core.exceptions import APIQueryParamsError
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
        elif group_by:
            raise APIQueryParamsError(
                "Valid sort params with group by are: key or count"
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
