from urllib.parse import unquote

from elasticsearch_dsl import MultiSearch, Q, Search
from flask import url_for

from core.exceptions import APIQueryParamsError
from core.utils import (get_country_name, get_display_name, get_field,
                        map_filter_params)


def shared_filter_view(params, fields_dict, index_name):
    """View used for filters view such as /works/filters/display_name.search:hello"""
    filter_params = map_filter_params(params)

    ms = MultiSearch(index=index_name)

    # filter
    if filter_params:
        ms, meta_results = filter_records_filters_view(
            fields_dict, filter_params, ms, index_name
        )
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
            # increment count if it is an OR query
            if len(meta["values"]) > 1 and meta["is_negated"]:
                idx = idx + 1
                value["count"] = 0
            elif len(meta["values"]) > 1:
                idx = idx + 1
                value["count"] = responses[idx].hits.total.value
            else:
                value["count"] = responses[idx].hits.total.value

            value["db_response_time_ms"] = responses[idx].took
        results["filters"].append(meta)
    return results


def filter_records_filters_view(fields_dict, filter_params, ms, index_name):
    meta_results = []
    s = Search()
    s = s.extra(track_total_hits=True, size=0)
    regular_queries = []

    # first pass with no OR queries
    for filter in filter_params:
        for key, value in filter.items():
            if "|" in value:
                continue

            field = get_field(fields_dict, key)
            field_meta = {"key": key, "type": type(field).__name__, "values": []}

            if value.startswith("!"):
                value = value[1:]
                field.value = value  # pass value without negation
                field_meta["is_negated"] = True
            else:
                field.value = value
                field_meta["is_negated"] = False
            q = field.build_query()
            field_meta["values"].append(
                {
                    "value": value,
                    "display_name": set_display_name(value, field),
                    # "url": set_url(search_param, key, value, index_name),
                }
            )
            regular_queries.append(q)
            meta_results.append(field_meta)
    combined_query = Q("bool", must=regular_queries)
    ms = ms.add(s.query(combined_query))

    # second pass for OR queries
    for filter in filter_params:
        for key, value in filter.items():
            # OR queries have | in the param values
            if "|" in value:
                field = get_field(fields_dict, key)
                field_meta = {"key": key, "type": type(field).__name__, "values": []}

                if value.startswith("!"):
                    field_meta["is_negated"] = True
                    value = value.replace("!", "")
                else:
                    field_meta["is_negated"] = False

                for or_value in value.split("|"):
                    validate_or_value(or_value)
                    field.value = or_value
                    q = field.build_query()

                    s = Search()
                    s = s.extra(track_total_hits=True, size=0)
                    s = s.query(combined_query)
                    s = s.query(q)
                    ms = ms.add(s)

                    field_meta["values"].append(
                        {
                            "value": or_value,
                            "display_name": set_display_name(or_value, field),
                            # "url": set_url(search_param, key, or_value, index_name),
                        }
                    )
                meta_results.append(field_meta)
    return ms, meta_results


def validate_or_value(or_value):
    if or_value.startswith("!"):
        raise APIQueryParamsError(
            f"The ! operator can only be used at the beginning of an OR query, "
            f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
            f"value: {or_value}"
        )


def set_url(search_param, key, value, index_name):
    search_string = None
    s_key = None

    if search_param:
        for s_key, s_value in search_param.items():
            search_string = f"{s_key}:{s_value}"

    if search_string and s_key == key:
        params = f"{search_string}"
    else:
        params = f"{search_string},{key}:{value}" if search_string else f"{key}:{value}"

    if index_name.startswith("authors"):
        url = url_for("authors.authors", filter=params, _external=True)
    elif index_name.startswith("concepts"):
        url = url_for("concepts.concepts", filter=params, _external=True)
    elif index_name.startswith("institutions"):
        url = url_for("institutions.institutions", filter=params, _external=True)
    elif index_name.startswith("venues"):
        url = url_for("venues.venues", filter=params, _external=True)
    elif index_name.startswith("works"):
        url = url_for("works.works", filter=params, _external=True)
    else:
        url = None
    url = unquote(url)

    # correct api endpoint:
    url = url.replace("elastic.api.openalex.org", "api.openalex.org")
    return url


def set_display_name(value, field):
    if type(field).__name__ == "OpenAlexIDField":
        display_name = get_display_name(value)
    elif field.param.endswith("country_code") or field.param.endswith("country-code"):
        display_name = get_country_name(value.lower())
    else:
        display_name = value
    return display_name
