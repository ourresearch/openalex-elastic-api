from collections import OrderedDict

import iso3166
from elasticsearch_dsl import A, Q, Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE
from autocomplete.validate import validate_entity_autocomplete_params
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import full_search
from core.utils import map_filter_params
from settings import (AUTHORS_INDEX, CONCEPTS_INDEX, INSTITUTIONS_INDEX,
                      VENUES_INDEX, WORKS_INDEX)

AUTOCOMPLETE_FILTER_DICT = {
    "alternate_host_venues.id": "alternate_host_venues.id",
    "alternate_host_venues.license": "alternate_host_venues.license",
    "alternate_host_venues.type": "alternate_host_venues.type",
    "authorships.author.id": "authorships.author.id",
    "authorships.institutions.country_code": "authorships.institutions.country_code",
    "authorships.institutions.id": "authorships.institutions.id",
    "authorships.institutions.type": "authorships.institutions.type",
    "cited_by_count": "cited_by_count",
    "concepts.id": "concepts.id",
    "has_abstract": "abstract",
    "has_doi": "ids.doi",
    "has_ngrams": "fulltext",
    "is_paratext": "is_paratext",
    "is_retracted": "is_retracted",
    "open_access.is_oa": "open_access.is_oa",
    "host_venue.id": "host_venue.id",
    "host_venue.license": "host_venue.license",
    "host_venue.publisher": "host_venue.publisher.lower",
    "host_venue.type": "host_venue.type",
    "open_access.oa_status": "open_access.oa_status",
    "publication_year": "publication_year",
    "type": "type",
}

HAS_FILTERS = ["has_abstract", "has_doi", "has_ngrams"]

BOOLEAN_FILTERS = ["is_paratext", "is_retracted", "open_access.is_oa"]

CITED_FILTER = ["cited_by_count"]


def autocomplete_filter(view_filter, fields_dict, index_name, request):
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")
    group_size = 10
    page_size = 10

    # error checking
    valid_filters = AUTOCOMPLETE_FILTER_DICT.keys()
    if view_filter not in valid_filters:
        raise APIQueryParamsError(
            f"The filter {view_filter} is not a valid filter. Current filters are: {', '.join(valid_filters)}"
        )
    combined_boolean_filters = BOOLEAN_FILTERS + HAS_FILTERS + CITED_FILTER

    if (
        view_filter.lower() in combined_boolean_filters
        and q
        or view_filter.lower() in combined_boolean_filters
        and q == ""
    ):
        raise APIQueryParamsError(
            "Cannot use q parameter with boolean or number filters."
        )

    if (
        view_filter.lower() not in combined_boolean_filters
        and not q
        and view_filter.lower() not in combined_boolean_filters
        and q != ""
    ):
        raise APIQueryParamsError("Need q param for this parameter.")

    # search
    s = Search(index=WORKS_INDEX)
    s = s.source(AUTOCOMPLETE_SOURCE)
    s = s.params(preference="autocomplete_group_by")

    if search and search != '""':
        s = full_search(index_name, s, search)

    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    # query
    if view_filter == "authorships.author.id":
        field_underscore = "authorships__author__display_name__autocomplete"
    elif view_filter == "authorships.institutions.id":
        field_underscore = "authorships__institutions__display_name__autocomplete"
    elif view_filter == "concepts.id":
        field_underscore = "concepts__display_name__autocomplete"
    elif view_filter == "host_venue.id":
        field_underscore = "host_venue__display_name__autocomplete"
    elif view_filter == "host_venue.publisher":
        field_underscore = "host_venue__publisher__autocomplete"
    elif view_filter == "alternate_host_venues.id":
        field_underscore = "alternate_host_venues__display_name"
    else:
        field_underscore = AUTOCOMPLETE_FILTER_DICT[view_filter].replace(".", "__")
    if view_filter in BOOLEAN_FILTERS:
        q = ""

    if q:
        if view_filter == "authorships.institutions.country_code":
            q = q.upper().strip()
        elif view_filter == "alternate_host_venues.id":
            q = q.title().replace("Of", "of")
        else:
            q = q.lower().strip()

        if view_filter == "concepts.id":
            group_size = 100
        else:
            group_size = 50
        page_size = 10
        if view_filter == "authorships.institutions.country_code":
            country_codes = country_search(q)
            s = s.query("terms", **{field_underscore: country_codes})
        elif view_filter == "publication_year":
            min_year, max_year = set_year_min_max(q)
            kwargs = {field_underscore: {"gte": min_year, "lte": max_year}}
            s = s.query("range", **kwargs)
        elif (
            "autocomplete" in field_underscore
            and view_filter == "authorships.author.id"
        ):
            s = s.query(
                "match_phrase_prefix", **{field_underscore: {"query": q, "slop": 1}}
            )
        elif "autocomplete" in field_underscore:
            s = s.query("match_phrase_prefix", **{field_underscore: q})
        else:
            s = s.query("prefix", **{field_underscore: q})

    # group
    results = []
    if view_filter.lower() in HAS_FILTERS:
        response, results = group_has_filter(results, s, view_filter)
    else:
        group = A(
            "terms", field=AUTOCOMPLETE_FILTER_DICT[view_filter], size=group_size
        ).metric(
            "top_hit",
            "top_hits",
            size=1,
            _source=[
                "authorships",
                "display_name",
                "host_venue",
                "concepts",
                "alternate_host_venues",
            ],
        )
        s.aggs.bucket("autocomplete_group", group)
        response = s.execute()
        for i in response.aggregations.autocomplete_group.buckets:
            id_key = set_key(i, view_filter)

            if view_filter == "alternate_host_venues.id":
                display_value = get_alternate_host_name(i)
            elif view_filter == "authorships.institutions.country_code":
                display_value = get_country_name(i.key)
            elif view_filter == "authorships.author.id":
                display_value = get_author_display_name(i)
            elif view_filter == "authorships.institutions.id":
                display_value = get_institution_display_name(i)
            elif view_filter == "concepts.id":
                display_value = get_concept_display_name(i)
            elif view_filter == "host_venue.id":
                display_value = get_host_venue_display_name(i)
            else:
                display_value = id_key

            if view_filter == "authorships.author.id":
                if all(x in str(display_value).lower() for x in q.lower().split()):
                    results.append(
                        {
                            "value": id_key,
                            "display_value": display_value,
                            "works_count": i.doc_count,
                        }
                    )
            elif q:
                if q.lower() in str(display_value).lower():
                    results.append(
                        {
                            "value": id_key,
                            "display_value": display_value,
                            "works_count": i.doc_count,
                        }
                    )
            else:
                results.append(
                    {
                        "value": id_key,
                        "display_value": display_value,
                        "works_count": i.doc_count,
                    }
                )

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": page_size,
    }
    result["filters"] = results[:page_size]
    return result


def group_has_filter(results, s, view_filter):
    exists = A("filter", Q("exists", field=AUTOCOMPLETE_FILTER_DICT[view_filter]))
    not_exists = A("filter", ~Q("exists", field=AUTOCOMPLETE_FILTER_DICT[view_filter]))
    s.aggs.bucket("exists", exists)
    s.aggs.bucket("not_exists", not_exists)
    response = s.execute()
    exists_count = response.aggregations.exists.doc_count
    not_exists_count = response.aggregations.not_exists.doc_count
    if exists_count:
        results.append(
            {
                "value": "true",
                "display_value": "true",
                "works_count": exists_count,
            }
        )
    if not_exists_count:
        results.append(
            {
                "value": "false",
                "display_value": "false",
                "works_count": not_exists_count,
            }
        )
    return response, results


def country_search(q):
    country_names = [n for n in iso3166.countries_by_name.keys()]
    matching_country_codes = []
    for country_name in country_names:
        if country_name.startswith(q.upper()):
            matching_country_codes.append(
                iso3166.countries_by_name[country_name].alpha2
            )
    return matching_country_codes


def get_country_name(country_code):
    country = iso3166.countries.get(country_code)
    return country.name


def set_year_min_max(q):
    min_year = 1000
    max_year = 3000
    if str(q).startswith("1") and len(q) == 1:
        min_year = 1000
        max_year = 1999
    elif str(q).startswith("2") and len(q) == 1:
        min_year = 2000
        max_year = 2999
    elif len(q) == 2:
        min_year = int(q) * 100
        max_year = int(q) * 100 + 99
    elif len(q) == 3:
        min_year = int(q) * 10
        max_year = int(q) * 10 + 9
    elif len(q) == 4:
        min_year = int(q)
        max_year = int(q)
    return min_year, max_year


def set_key(i, view_filter):
    value = i.key
    if view_filter != "cited_by_count":
        if i.key == 1:
            value = "true"
        elif i.key == 0:
            value = "false"
    return value


def get_author_display_name(i):
    authorships = i.top_hit.hits.hits[0]["_source"]["authorships"]
    for author in authorships:
        if author["author"]["id"] == i.key:
            return author["author"]["display_name"]


def get_institution_display_name(i):
    authorships = i.top_hit.hits.hits[0]["_source"]["authorships"]
    for author in authorships:
        for institution in author["institutions"]:
            if institution["id"] == i.key:
                return institution["display_name"]


def get_host_venue_display_name(i):
    return i.top_hit.hits.hits[0]["_source"]["host_venue"]["display_name"]


def get_concept_display_name(i):
    concepts = i.top_hit.hits.hits[0]["_source"]["concepts"]
    for concept in concepts:
        if concept["id"] == i.key:
            return concept["display_name"]


def get_alternate_host_name(i):
    venues = i.top_hit.hits.hits[0]["_source"]["alternate_host_venues"]
    for venue in venues:
        if venue["id"] == i.key:
            return venue["display_name"]
