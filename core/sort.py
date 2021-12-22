from core.exceptions import APIQueryParamsError
from works.fields import fields


def sort_records(sort_params, s):
    for field in fields:
        if field.param in sort_params:
            param = sort_params[field.param]
            if param == "asc":
                s = s.sort(field.es_field())
            elif param == "desc":
                s = s.sort(f"-{field.es_field()}")
            else:
                raise APIQueryParamsError(
                    f"Sort value for param {field.param} must be asc or desc."
                )
    return s
