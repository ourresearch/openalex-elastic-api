import re

from elasticsearch_dsl import Search
from iso3166 import countries

import settings
from core.exceptions import APIQueryParamsError
from settings import (
    AUTHORS_INDEX,
    CONCEPTS_INDEX,
    INSTITUTIONS_INDEX,
    PUBLISHERS_INDEX,
    SOURCES_INDEX,
    VENUES_INDEX,
    WORKS_INDEX,
)


def get_valid_fields(fields_dict):
    valid_fields = sorted(list(fields_dict.keys()))
    valid_fields.remove("from_updated_date")
    return valid_fields


def get_field(fields_dict, key):
    try:
        field = fields_dict[key]
        return field
    except KeyError:
        valid_fields = get_valid_fields(fields_dict)
        raise APIQueryParamsError(
            f"{key} is not a valid field. Valid fields are underscore or hyphenated versions of: {', '.join(valid_fields)}"
        )


def map_filter_params(filter_params):
    """
    Split filter params by comma, then map to a dictionary based on key:value.
    """
    if filter_params:
        try:
            results = []
            params = filter_params.split(",")
            for param in params:
                key, value = param.split(":", 1)
                key = key.replace("-", "_")  # convert key to underscore
                results.append({key: value})
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        results = None
    return results


def map_sort_params(param):
    """
    Split sort params by comma, then map to a dictionary based on key:value.
    Assign default value of "asc" if no value specificed after the colon.
    """
    if param:
        try:
            result = {}
            params = param.split(",")
            # parse params and set asc as default
            for param in params:
                key, value = param.split(":") if ":" in param else (param, "asc")
                key = key.replace("-", "_")
                result[key] = value
        except ValueError:
            raise APIQueryParamsError(f"Invalid query parameter in {param}.")
    else:
        result = None
    return result


def convert_group_by(response, field):
    """
    Convert to key, doc_count dictionary
    """
    if not response.hits.hits:
        return []
    r = response.hits.hits[0]._source.to_dict()
    stats = r.get(field)
    result = [{"key": key, "doc_count": count} for key, count in stats.items()]
    result_sorted = sorted(
        result, key=lambda i: i["doc_count"], reverse=True
    )  # sort by count
    return result_sorted


def set_number_param(request, param, default):
    """
    Tries to get a number param with hyphen or underscore. Returns an error if not a number.
    """
    result = request.args.get(param) or request.args.get(param.replace("-", "_"))
    if result:
        try:
            result = int(result)
        except ValueError:
            raise APIQueryParamsError(f"Param {param} must be a number.")
    else:
        result = default
    return result


def get_index_name_by_id(openalex_id):
    """Takes an openalex ID and returns an appropriate index."""
    clean_id = normalize_openalex_id(openalex_id)
    if not clean_id:
        error_id = f"'{openalex_id.replace('https://openalex.org/', '')}'"
        raise APIQueryParamsError(f"{error_id} is not a valid OpenAlex ID.")
    index_name = None
    if clean_id.startswith("A"):
        index_name = AUTHORS_INDEX
    elif clean_id.startswith("C"):
        index_name = CONCEPTS_INDEX
    elif clean_id.startswith("I"):
        index_name = INSTITUTIONS_INDEX
    elif clean_id.startswith("P"):
        index_name = PUBLISHERS_INDEX
    elif clean_id.startswith("S"):
        index_name = SOURCES_INDEX
    elif clean_id.startswith("V"):
        index_name = VENUES_INDEX
    elif clean_id.startswith("W"):
        index_name = WORKS_INDEX
    return index_name


def normalize_openalex_id(openalex_id):
    if not openalex_id:
        return None
    openalex_id = openalex_id.strip().upper()
    p = re.compile("([WAICFVPS]\d{2,})")
    matches = re.findall(p, openalex_id)
    if len(matches) == 0:
        return None
    clean_openalex_id = matches[0]
    clean_openalex_id = clean_openalex_id.replace("\0", "")
    return clean_openalex_id


def get_full_openalex_id(openalex_id):
    short_openalex_id = normalize_openalex_id(openalex_id)
    if short_openalex_id:
        full_openalex_id = f"https://openalex.org/{short_openalex_id}"
    else:
        full_openalex_id = None
    return full_openalex_id


def is_cached(request):
    bypass_cache = request.args.get("bypass_cache") == "true"
    # cache urls with group-by
    if (
        (request.args.get("group_by") or request.args.get("group-by"))
        and not request.args.get("format")
        and not bypass_cache
        and not settings.DEBUG
    ):
        cached = True
    else:
        cached = False
    return cached


def get_country_name(country_id):
    try:
        country = countries.get(country_id.lower())
    except KeyError:
        country = None
    return country.name if country else country_id


def process_only_fields(request, schema):
    schema_fields = [f for f in schema._declared_fields]
    only_fields = request.args.get("select")
    if only_fields:
        only_fields = only_fields.split(",")
        for field in only_fields:
            if field.strip() not in schema_fields:
                raise APIQueryParamsError(
                    f"{field} is not a valid select field. Valid fields for select are: {', '.join(schema_fields)}."
                )
        only_fields = [f"results.{field.strip()}" for field in only_fields]
        # add back meta and group_by fields
        only_fields.insert(0, "meta")
        only_fields.append("group_by")
    return only_fields


def dump_field_names_recurse(field, collected=None, prefix=None):
    if collected is None:
        collected = []
    if prefix is None:
        prefix = []
    if hasattr(field, "schema"):
        prefix = prefix + [field.name]
        for field2 in field.schema.fields.values():
            collected = dump_field_names_recurse(field2, collected, prefix=prefix)
    else:
        item = ".".join(prefix + [field.name])
        collected.append(item)
    return collected


def get_flattened_fields(schema):
    fields = schema.fields
    flattened_fields = []
    for field in fields.values():
        flattened_fields.extend(dump_field_names_recurse(field))
    return flattened_fields


def get_display_name(openalex_id):
    """Takes an openalex id and returns a single display name."""
    if not openalex_id:
        return None
    elif openalex_id == "null":
        return "unknown"

    if "https://openalex.org" not in openalex_id:
        openalex_id = f"https://openalex.org/{openalex_id}"

    index_name = get_index_name_by_id(openalex_id)
    s = Search(index=index_name)
    s = s.filter("term", ids__openalex__lower=openalex_id)
    response = s.execute()

    if response:
        display_name = response[0].display_name
    else:
        display_name = None
    return display_name
