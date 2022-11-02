from urllib.parse import unquote

from elasticsearch_dsl import MultiSearch, Q, Search
from flask import url_for

import settings
from core.exceptions import APIQueryParamsError
from core.search import full_search
from core.utils import (get_country_name, get_display_name, get_field,
                        map_filter_params)


def shared_filter_view(request, params, fields_dict, index_name):
    """View used for filters view such as /works/filters/display_name.search:hello"""
    filter_params = map_filter_params(params)
    search = request.args.get("search")
    if search and search != '""':
        filter_params.append({"search": search})

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
            if len(meta["values"]) > 1 and meta["is_negated"]:
                idx = idx + 1
                value["count"] = 0
            elif len(meta["values"]) > 1 and meta["is_negated"] == False:
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

    # first pass apply entire query, but do not add OR values to meta response
    for filter in filter_params:
        for key, value in filter.items():
            # handle full search differently
            if key == "search":
                s = full_search(index_name, s, value)
                field_meta = {"key": key, "type": "FullSearchField", "values": []}
                field_meta["values"].append(
                    {
                        "value": value,
                        "display_name": value,
                        # "url": set_url(search_param, key, or_value, index_name),
                    }
                )
                meta_results.append(field_meta)
                break

            field = get_field(fields_dict, key)

            # OR queries have | in the param values
            if "|" in value:
                or_queries = []

                if value.startswith("!"):
                    # negate everything in values after !, like: NOT (42 or 43)
                    for or_value in value.split("|"):
                        or_value = or_value.replace("!", "")
                        field.value = or_value
                        q = field.build_query()
                        not_query = ~Q("bool", must=q)
                        s = s.query(not_query)
                else:
                    # standard OR query, like: 42 or 43
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
                    combined_or_query = Q(
                        "bool", should=or_queries, minimum_should_match=1
                    )
                    s = s.query(combined_or_query)

            # everything else is an AND query
            else:
                field_meta = {"key": key, "type": type(field).__name__, "values": []}
                field.value = value
                if field.value.startswith("!"):
                    field_meta["is_negated"] = True
                    field.value = field.value.replace("!", "")
                else:
                    field_meta["is_negated"] = False
                field_meta["values"].append(
                    {
                        "value": field.value,
                        "display_name": set_display_name(field.value, field),
                        # "url": set_url(search_param, key, or_value, index_name),
                    }
                )
                q = field.build_query()
                s = s.query(q)
                meta_results.append(field_meta)
    ms = ms.add(s)

    # second pass, process each OR value as an AND query and add to meta response
    i = 0
    or_s = {}
    for filter in filter_params:
        for key, value in filter.items():

            # OR queries have | in the param values
            if "|" in value:
                field = get_field(fields_dict, key)
                field_meta = {"key": key, "type": type(field).__name__, "values": []}

                if value.startswith("!"):
                    field_meta["is_negated"] = True
                    # negate everything in values after !, like: NOT (42 or 43)
                    for or_value in value.split("|"):
                        or_s[i] = s

                        or_value = or_value.replace("!", "")
                        field_meta["values"].append(
                            {
                                "value": or_value,
                                "display_name": set_display_name(or_value, field),
                                # "url": set_url(search_param, key, or_value, index_name),
                            }
                        )
                        field.value = or_value
                        q = field.build_query()
                        not_query = ~Q("bool", must=q)
                        or_s[i] = or_s[i].query(not_query)
                        ms = ms.add(or_s[i])
                        i = i + 1
                    meta_results.append(field_meta)
                else:
                    field_meta["is_negated"] = False
                    # standard OR query, like: 42 or 43
                    for or_value in value.split("|"):
                        or_s[i] = s
                        if or_value.startswith("!"):
                            raise APIQueryParamsError(
                                f"The ! operator can only be used at the beginning of an OR query, "
                                f"like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
                                f"value: {or_value}"
                            )
                        field_meta["values"].append(
                            {
                                "value": or_value,
                                "display_name": set_display_name(or_value, field),
                                # "url": set_url(search_param, key, or_value, index_name),
                            }
                        )
                        field.value = or_value
                        q = field.build_query()
                        or_s[i] = or_s[i].query(q)
                        ms = ms.add(or_s[i])
                        i = i + 1
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
    elif field.param.endswith("continent"):
        display_name = ""
        for continent in settings.CONTINENT_NAMES:
            if (
                value.lower() == continent["id"].lower()
                or value.lower() == continent["param"]
            ):
                display_name = continent["display_name"]
                break
    else:
        display_name = value
    return display_name
