from datetime import datetime

from core.exceptions import APIQueryParamsError


def filter_records(field, s):
    # range query
    if field.is_range_query:
        s = execute_range_query(field, s)

    # date query
    elif field.is_date_query:
        s = execute_date_query(field, s)

    # boolean query
    elif field.is_bool_query:
        s = execute_boolean_query(field, s)

    # regular query
    else:
        s = execute_regular_query(field, s)
    return s


def execute_regular_query(field, s):
    if field.value == "null":
        field_name = field.es_field()
        field_name = field_name.replace("__", ".")
        s = s.exclude("exists", field=field_name)
    elif field.value == "country_code":
        query = field.value.upper()
        kwargs = {field.es_field(): query}
        s = s.filter("term", **kwargs)
    else:
        query = field.value.lower().split(" ")
        kwargs = {field.es_field(): query}
        s = s.filter("terms", **kwargs)
    return s


def execute_boolean_query(field, s):
    if field.value == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        kwargs = {field.es_field(): field.value.lower()}
        s = s.filter("term", **kwargs)
    return s


def execute_date_query(field, s):
    if "<" in field.value:
        query = field.value[1:]
        validate_date_param(field, query)
        kwargs = {field.es_field(): {"lte": query}}
        s = s.filter("range", **kwargs)
    elif ">" in field.value:
        query = field.value[1:]
        validate_date_param(field, query)
        kwargs = {field.es_field(): {"gt": query}}
        s = s.filter("range", **kwargs)
    elif field.value == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        validate_date_param(field, field.value)
        kwargs = {field.es_field(): field.value}
        s = s.filter("term", **kwargs)
    return s


def execute_range_query(field, s):
    if "<" in field.value:
        query = field.value[1:]
        validate_range_param(field, query)
        kwargs = {field.es_field(): {"lte": int(query)}}
        s = s.filter("range", **kwargs)
    elif ">" in field.value:
        query = field.value[1:]
        validate_range_param(field, query)
        kwargs = {field.es_field(): {"gt": int(query)}}
        s = s.filter("range", **kwargs)
    elif field.value == "null":
        s = s.exclude("exists", field=field.es_field())
    else:
        validate_range_param(field, field.value)
        kwargs = {field.es_field(): field.value}
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
