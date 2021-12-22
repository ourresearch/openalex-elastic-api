from datetime import datetime

from core.exceptions import APIQueryParamsError
from works.fields import fields


def filter_records(filter_params, s):
    for field in fields:

        # range query
        if field.param in filter_params and field.is_range_query:
            s = execute_range_query(field, filter_params, s)

        # date query
        elif field.param in filter_params and field.is_date_query:
            s = execute_date_query(field, filter_params, s)

        # boolean query
        elif field.param in filter_params and field.is_bool_query:
            s = execute_boolean_query(field, filter_params, s)

        # regular query
        elif field.param in filter_params:
            s = execute_regular_query(field, filter_params, s)
    return s


def execute_regular_query(field, filter_params, s):
    param = filter_params[field.param]
    if param == "null":
        field = field.es_field()
        field = field.replace("__", ".")
        s = s.exclude("exists", field=field)
    elif "country_code" in field.param:
        param = param.upper()
        kwargs = {field.es_field(): param}
        s = s.filter("term", **kwargs)
    else:
        param = param.lower().split(" ")
        kwargs = {field.es_field(): param}
        s = s.filter("terms", **kwargs)
    return s


def execute_boolean_query(field, filter_params, s):
    param = filter_params[field.param]
    param = param.lower()
    if param == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        kwargs = {field.es_field(): param}
        s = s.filter("term", **kwargs)
    return s


def execute_date_query(field, filter_params, s):
    param = filter_params[field.param]
    if "<" in param:
        param = param[1:]
        validate_date_param(field, param)
        kwargs = {field.es_field(): {"lte": param}}
        s = s.filter("range", **kwargs)
    elif ">" in param:
        param = param[1:]
        validate_date_param(field, param)
        kwargs = {field.es_field(): {"gt": param}}
        s = s.filter("range", **kwargs)
    elif param == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        validate_date_param(field, param)
        kwargs = {field.es_field(): param}
        s = s.filter("term", **kwargs)
    return s


def execute_range_query(field, filter_params, s):
    param = filter_params[field.param]
    if "<" in param:
        param = param[1:]
        validate_range_param(field, param)
        kwargs = {field.es_field(): {"lte": int(param)}}
        s = s.filter("range", **kwargs)
    elif ">" in param:
        param = param[1:]
        validate_range_param(field, param)
        kwargs = {field.es_field(): {"gt": int(param)}}
        s = s.filter("range", **kwargs)
    elif param == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        validate_range_param(field, param)
        kwargs = {field.es_field(): param}
        s = s.filter("term", **kwargs)
    return s


def validate_range_param(field, param):
    try:
        param = int(param)
    except ValueError:
        raise APIQueryParamsError(f"Value for param {field.param} must be a number.")


def validate_date_param(field, param):
    try:
        date = datetime.strptime(param, "%Y-%m-%d")
    except ValueError:
        raise APIQueryParamsError(
            f"Value for param {field.param} must be a date in format 2020-05-17."
        )
