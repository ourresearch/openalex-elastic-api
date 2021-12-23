from core.exceptions import APIQueryParamsError
from works.fields import fields


def sort_records(field, s):
    if field.value == "asc":
        s = s.sort(field.es_sort_field())
    elif field.value == "desc":
        s = s.sort(f"-{field.es_sort_field()}")
    else:
        raise APIQueryParamsError(
            f"Sort value for param {field.param} must be asc or desc."
        )
    return s
