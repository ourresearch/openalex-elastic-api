from elasticsearch_dsl import MultiSearch, Q, Search

from core.exceptions import APIQueryParamsError
from core.utils import (get_country_name, get_display_name, get_field,
                        map_filter_params)


def shared_filter_view(params, fields_dict, index_name):
    """View used for filters view such as /works/filters/display_name.search:hello"""
    filter_params = map_filter_params(params)

    ms = MultiSearch(index=index_name)

    # filter
    if filter_params:
        ms, meta_results = filter_records_filters_view(fields_dict, filter_params, ms)
    else:
        raise APIQueryParamsError(
            "Must include filter values in order to use this endpoint. Example: /works/filters?filter=oa_status:gold"
        )

    responses = ms.execute()

    results = {"filters": []}

    # iterate through responses and match them to meta results.
    idx = 0
    for meta in meta_results:
        for value in meta["values"]:
            value["count"] = responses[idx].hits.total.value
            value["db_response_time_ms"] = responses[idx].took
            idx = idx + 1
        results["filters"].append(meta)
    return results


def filter_records_filters_view(fields_dict, filter_params, ms):
    meta_results = []
    search_param = get_search_param(filter_params)
    search_query = None
    if search_param:
        # build search query
        for key, value in search_param.items():
            field = get_field(fields_dict, key)
            field.value = value
            search_query = field.build_query()

    for filter in filter_params:
        for key, value in filter.items():
            field = get_field(fields_dict, key)

            field_meta = {"key": key, "type": type(field).__name__, "values": []}

            # OR queries have | in the param values
            if "|" in value:
                if value.startswith("!"):
                    field_meta["is_negated"] = True
                    value = value.replace("!", "")
                else:
                    field_meta["is_negated"] = False

                for or_value in value.split("|"):
                    validate_or_value(or_value)
                    field.value = or_value
                    field_meta["values"].append(
                        {
                            "value": or_value,
                            "display_name": set_display_name(or_value, field),
                        }
                    )
                    ms = execute_ms_search(field, ms, search_query)
            else:
                if value.startswith("!"):
                    value = value[1:]
                    field.value = value  # pass value without negation
                    field_meta["is_negated"] = True
                else:
                    field.value = value
                    field_meta["is_negated"] = False
                field_meta["values"].append(
                    {"value": value, "display_name": set_display_name(value, field)}
                )
                ms = execute_ms_search(field, ms, search_query)
            meta_results.append(field_meta)
    return ms, meta_results


def validate_or_value(or_value):
    if or_value.startswith("!"):
        raise APIQueryParamsError(
            f"The ! operator can only be used at the beginning of an OR query, "
            f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
            f"value: {or_value}"
        )


def execute_ms_search(field, ms, search_query):
    """If a search query is present, combine it with the current filter."""
    q = field.build_query()
    s = Search()
    s = s.extra(track_total_hits=True, size=0)
    if search_query:
        combined_query = Q("bool", must=[q, search_query])
        ms = ms.add(s.query(combined_query))
    else:
        ms = ms.add(s.query(q))
    return ms


def get_search_param(filter_params):
    """Find and return a search param."""
    search_param = None
    for filter in filter_params:
        for key, value in filter.items():
            if key == "display_name.search" or key == "title.search":
                search_param = {key: value}
    return search_param


def set_display_name(value, field):
    if type(field).__name__ == "OpenAlexIDField":
        display_name = get_display_name(value)
    elif field.param.endswith("country_code") or field.param.endswith("country-code"):
        display_name = get_country_name(value.lower())
    else:
        display_name = value
    return display_name
