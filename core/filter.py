from datetime import datetime

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.search import search_records
from core.utils import get_field


def filter_records(fields_dict, filter_params, s):
    for key, value in filter_params.items():
        field = get_field(fields_dict, key)
        field.value = value
        field.validate()
        if field.is_search_query:
            s = search_records(field.value, s)
        else:
            s = filter_field(field, s)
    return s


def filter_field(field, s):
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
    elif field.value == "!null":
        field_name = field.es_field()
        field_name = field_name.replace("__", ".")
        s = s.filter("exists", field=field_name)
    elif field.value.startswith("!"):
        query = field.value[1:]
        kwargs = {field.es_field(): query}
        s = s.exclude("match_phrase", **kwargs)
    elif (
        field.param.endswith(".id")
        or field.param == "cites"
        or field.param == "referenced_works"
    ) and (field.value.startswith("[") and field.value.endswith("]")):
        terms_to_filter = []
        values = field.value[1:-1].split(",")
        for value in values:
            if "https://openalex.org/" in field.value:
                terms_to_filter.append(value.strip())
            else:
                terms_to_filter.append(f"https://openalex.org/{value.strip().upper()}")
        kwargs = {field.es_field(): terms_to_filter}
        s = s.filter("terms", **kwargs)
    elif (
        field.param.endswith(".id")
        or field.param == "cites"
        or field.param == "referenced_works"
    ):
        if "https://openalex.org/" in field.value:
            kwargs = {field.es_field(): field.value}
            s = s.filter("term", **kwargs)
        else:
            query = f"https://openalex.org/{field.value.upper()}"
            kwargs = {field.es_field(): query}
            s = s.filter("term", **kwargs)
    elif "publisher" in field.param:
        if field.value.startswith("[") and field.value.endswith("]"):
            phrases_to_filter = field.value[1:-1].split(",")
            queries = []
            for phrase in phrases_to_filter:
                kwargs = {field.es_field(): phrase}
                queries.append(Q("match_phrase", **kwargs))
            q = Q("bool", should=queries, minimum_should_match=1)
            s = s.query(q)
        else:
            kwargs = {field.es_field(): field.value}
            s = s.filter("match_phrase", **kwargs)
    else:
        if field.value.startswith("[") and field.value.endswith("]"):
            terms_to_filter = field.value[1:-1].split(",")
            terms_to_filter_stripped = [term.strip() for term in terms_to_filter]
            kwargs = {field.es_field(): terms_to_filter_stripped}
            s = s.filter("terms", **kwargs)
        else:
            kwargs = {field.es_field(): field.value}
            s = s.filter("term", **kwargs)
    return s


def execute_boolean_query(field, s):
    if field.value == "null":
        s = s.exclude("exists", field=field.es_field())
    elif field.value == "!null":
        s = s.filter("exists", field=field.es_field())
    else:
        kwargs = {field.es_field(): field.value.lower()}
        s = s.filter("term", **kwargs)
    return s


def execute_date_query(field, s):
    if "<" in field.value:
        query = field.value[1:]
        validate_date_param(field, query)
        kwargs = {field.es_field(): {"lt": query}}
        s = s.filter("range", **kwargs)
    elif ">" in field.value:
        query = field.value[1:]
        validate_date_param(field, query)
        kwargs = {field.es_field(): {"gt": query}}
        s = s.filter("range", **kwargs)
    elif field.param == "to_publication_date":
        validate_date_param(field, field.value)
        kwargs = {field.es_field(): {"lte": field.value}}
        s = s.filter("range", **kwargs)
    elif field.param == "from_publication_date":
        validate_date_param(field, field.value)
        kwargs = {field.es_field(): {"gte": field.value}}
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
        kwargs = {field.es_field(): {"lt": int(query)}}
        s = s.filter("range", **kwargs)
    elif ">" in field.value:
        query = field.value[1:]
        validate_range_param(field, query)
        kwargs = {field.es_field(): {"gt": int(query)}}
        s = s.filter("range", **kwargs)
    elif "-" in field.value:
        values = field.value.strip().split("-")
        left_value = values[0]
        right_value = values[1]
        validate_range_param(field, left_value)
        validate_range_param(field, right_value)
        kwargs = {field.es_field(): {"gt": int(left_value), "lt": int(right_value)}}
        s = s.filter("range", **kwargs)
    elif field.value.startswith("[") and field.value.endswith("]"):
        terms_to_filter = field.value[1:-1].split(",")
        queries = []
        for term in terms_to_filter:
            validate_range_param(field, term)
            kwargs = {field.es_field(): term}
            queries.append(Q("term", **kwargs))
        q = Q("bool", should=queries, minimum_should_match=1)
        s = s.query(q)
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
