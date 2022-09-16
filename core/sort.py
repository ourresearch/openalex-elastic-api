import settings
from core.exceptions import APIQueryParamsError
from core.utils import get_field


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

        # all others
        field = get_field(fields_dict, key)
        if value == "asc":
            sort_fields.append(field.es_sort_field())
        elif value == "desc":
            sort_fields.append(f"-{field.es_sort_field()}")
    return sort_fields
