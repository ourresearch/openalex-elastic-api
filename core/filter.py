import re

from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError
from core.fields import TermField
from core.utils import get_field
from settings import MAX_IDS_IN_FILTER


def filter_records(fields_dict, filter_params, s, sample=None):
    for filter in filter_params:
        for key, value in filter.items():
            if key == 'include_xpac' or key == 'include-xpac':
                continue
            field = get_field(fields_dict, key)

            # multiple OR queries have | in the param values
            if "|" in value:
                s = handle_or_query(field, fields_dict, s, value, sample)

            # multiple AND queries have + in the param values which is converted to a space
            elif (
                " " in value
                and "search" not in field.param
                and type(field).__name__ != "RangeField"
                and type(field).__name__ != "BooleanField"
            ):
                s = handle_and_query(field, s, value)

            # everything else is a normal and query
            else:
                field.value = value
                q = field.build_query()
                if sample and "search" in field.param:
                    s = s.filter(q)
                elif "search" in field.param:
                    s = s.query(q)
                else:
                    s = s.filter(q)
    return s


def handle_or_query(field, fields_dict, s, value, sample):
    or_queries = []

    if len(value.split("|")) > MAX_IDS_IN_FILTER:
        raise APIQueryParamsError(
            f"Maximum number of values exceeded for {field.param}. Decrease values to {MAX_IDS_IN_FILTER} or "
            f"below, or consider downloading the full dataset at "
            f"https://docs.openalex.org/download-snapshot"
        )

    # raise error if trying to use | between filters like filter=institutions.country_code:fr|host_venue.issn:0957-1558
    fields = fields_dict.keys()
    for filter_field in fields:
        if filter_field in value:
            if filter_field and re.search(rf"{filter_field}:", value):
                raise APIQueryParamsError(
                    f"It looks like you're trying to do an OR query between filters and it's not supported. \n"
                    f"You can do this: institutions.country_code:fr|en, but not this: institutions.country_code:gb|host_venue.issn:0957-1558. \n"
                    f"Problem value: {value}"
                )

    if value.startswith("!"):
        # negate everything in values after !, like: NOT (42 or 43)
        for or_value in value.split("|"):
            or_value = or_value.replace("!", "")
            field.value = or_value
            q = field.build_query()
            not_query = ~Q("bool", must=q)
            if sample and "search" in field.param:
                s = s.filter(not_query)
            elif "search" in field.param:
                s = s.query(not_query)
            else:
                s = s.filter(not_query)
    else:
        # standard OR query, like: 42 or 43
        # Check if this is a TermField and use the more efficient terms query
        if isinstance(field, TermField):
            # Use the optimized terms query for TermField
            values = value.split("|")
            for or_value in values:
                if or_value.startswith("!"):
                    raise APIQueryParamsError(
                        f"The ! operator can only be used at the beginning of an OR query, "
                        f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                        f"value: {or_value}"
                    )
            # Build a single terms query instead of multiple term queries
            combined_or_query = field.build_terms_query(values)
            if sample and "search" in field.param:
                s = s.filter(combined_or_query)
            elif "search" in field.param:
                s = s.query(combined_or_query)
            else:
                s = s.filter(combined_or_query)
        else:
            # Fall back to the original bool/should approach for other field types
            for or_value in value.split("|"):
                if or_value.startswith("!"):
                    raise APIQueryParamsError(
                        f"The ! operator can only be used at the beginning of an OR query, "
                        f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                        f"value: {or_value}"
                    )
                field.value = or_value
                q = field.build_query()
                or_queries.append(q)
            combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
            if sample and "search" in field.param:
                s = s.filter(combined_or_query)
            elif "search" in field.param:
                s = s.query(combined_or_query)
            else:
                s = s.filter(combined_or_query)
    return s


def handle_and_query(field, s, value):
    and_queries = []

    if len(value.split(" ")) > MAX_IDS_IN_FILTER:
        raise APIQueryParamsError(
            f"Maximum number of values exceeded for {field.param}. Decrease values to {MAX_IDS_IN_FILTER} or "
            f"below, or consider downloading the full dataset at "
            f"https://docs.openalex.org/download-snapshot"
        )

    for and_value in value.split(" "):
        field.value = and_value
        q = field.build_query()
        and_queries.append(q)
    combined_and_query = Q("bool", must=and_queries)
    s = s.filter(combined_and_query)
    return s
