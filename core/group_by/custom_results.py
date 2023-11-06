from elasticsearch_dsl import MultiSearch, Search, Q

import settings
from core.filter import filter_records
from core.search import full_search_query
from countries import COUNTRIES_BY_CONTINENT


def group_by_continent(field, index_name, params, fields_dict):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for continent in COUNTRIES_BY_CONTINENT:
        s = search_and_filter(fields_dict, index_name, params)
        country_codes = [c["country_code"] for c in COUNTRIES_BY_CONTINENT[continent]]
        s = s.filter("terms", **{field.es_field(): country_codes})
        ms = ms.add(s)

    responses = ms.execute()

    for continent, response in zip(COUNTRIES_BY_CONTINENT.keys(), responses):
        if not params["q"] or params["q"] and params["q"].lower() in continent.lower():
            group_by_results.append(
                {
                    "key": settings.CONTINENT_PARAMS.get(
                        continent.lower().replace(" ", "_")
                    ),
                    "key_display_name": continent,
                    "doc_count": response.hits.total.value,
                }
            )
        took = took + response.took

    # get unknown
    s = Search(index=index_name)
    if params["search"] and params["search"] != '""':
        search_query = full_search_query(index_name, params["search"])
        s = s.query(search_query)

    # filter
    if params["filters"]:
        s = filter_records(fields_dict, params["filters"], s)
    s = s.query(~Q("exists", field=field.es_field()))
    response = s.execute()
    unknown_count = s.count()
    if (unknown_count and not params["q"]) or (
        unknown_count and params["q"] and params["q"].lower() in "unknown"
    ):
        group_by_results.append(
            {
                "key": "unknown",
                "key_display_name": "unknown",
                "doc_count": unknown_count,
            }
        )
    took = took + response.took

    # sort by count
    group_by_results = sorted(
        group_by_results, key=lambda d: d["doc_count"], reverse=True
    )
    return group_by_results


def group_by_version(field, index_name, params, known, fields_dict):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    for version in settings.VERSIONS:
        s = search_and_filter(fields_dict, index_name, params)
        if version == "null":
            s = s.filter(~Q("exists", field="locations.version"))
        else:
            kwargs1 = {"locations.version": version}
            s = s.query(Q("term", **kwargs1))
        ms = ms.add(s)

    responses = ms.execute()

    for version, response in zip(settings.VERSIONS, responses):
        version = "unknown" if version == "null" else version
        key_display_name = "unknown" if version == "null" else version
        if key_display_name == "unknown" and known:
            continue
        if not params["q"] or params["q"] and params["q"].lower() in version.lower():
            group_by_results.append(
                {
                    "key": version,
                    "key_display_name": key_display_name,
                    "doc_count": response.hits.total.value,
                }
            )
        took = took + response.took

    # sort by count
    group_by_results = sorted(
        group_by_results, key=lambda d: d["doc_count"], reverse=True
    )
    return group_by_results


def group_by_best_open_version(field, index_name, params, fields_dict):
    group_by_results = []
    took = 0
    ms = MultiSearch(index=index_name)
    versions = ["any", "acceptedOrPublished", "published"]
    for version in versions:
        s = search_and_filter(fields_dict, index_name, params)
        submitted_query = Q("term", best_oa_location__version="submittedVersion")
        accepted_query = Q("term", best_oa_location__version="acceptedVersion")
        published_query = Q("term", best_oa_location__version="publishedVersion")
        if version == "any":
            query = submitted_query | accepted_query | published_query
        elif version == "acceptedOrPublished":
            query = accepted_query | published_query
        elif version == "published":
            query = published_query
        ms = ms.add(s.filter(query))

    responses = ms.execute()

    for version, response in zip(versions, responses):
        key_display_name = version
        if not params["q"] or params["q"] and params["q"].lower() in version.lower():
            group_by_results.append(
                {
                    "key": version,
                    "key_display_name": key_display_name,
                    "doc_count": response.hits.total.value,
                }
            )
        took = took + response.took

    # sort by count
    group_by_results = sorted(
        group_by_results, key=lambda d: d["doc_count"], reverse=True
    )

    return group_by_results


def search_and_filter(fields_dict, index_name, params):
    s = Search()
    if params["search"] and params["search"] != '""':
        search_query = full_search_query(index_name, params["search"])
        s = s.query(search_query)
    # filter
    if params["filters"]:
        s = filter_records(fields_dict, params["filters"], s)
    s = s.extra(track_total_hits=True)
    return s
