from collections import OrderedDict
from datetime import date

import iso3166
from elasticsearch_dsl import A, Q, Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE
from autocomplete.validate import validate_entity_autocomplete_params
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import full_search
from core.utils import map_filter_params
from settings import (AUTHORS_INDEX, INSTITUTIONS_INDEX, VENUES_INDEX,
                      WORKS_INDEX)

AUTOCOMPLETE_FILTER_DICT = {
    "authorships.author.id": "authorships.author.id",
    "authorships.institutions.country_code": "authorships.institutions.country_code",
    "authorships.institutions.id": "authorships.institutions.id",
    "authorships.institutions.type": "authorships.institutions.type",
    "has_abstract": "abstract",
    "has_doi": "ids.doi",
    "has_ngrams": "fulltext",
    "is_paratext": "is_paratext",
    "is_retracted": "is_retracted",
    "open_access.is_oa": "open_access.is_oa",
    "host_venue.display_name": "host_venue.id",
    "host_venue.license": "host_venue.license",
    "host_venue.publisher": "host_venue.publisher.lower",
    "host_venue.type": "host_venue.type",
    "open_access.oa_status": "open_access.oa_status",
    "publication_year": "publication_year",
    "type": "type",
}

HAS_FILTERS = ["has_abstract", "has_doi", "has_ngrams"]

BOOLEAN_FILTERS = ["is_paratext", "is_retracted", "open_access.is_oa"]


def autocomplete_filter(view_filter, fields_dict, index_name, request):
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")
    group_size = 200
    page_size = 200

    # error checking
    valid_filters = AUTOCOMPLETE_FILTER_DICT.keys()
    if view_filter not in valid_filters:
        raise APIQueryParamsError(
            f"The filter {view_filter} is not a valid filter. Current filters are: {', '.join(valid_filters)}"
        )
    combined_boolean_filters = BOOLEAN_FILTERS + HAS_FILTERS

    if (
        view_filter.lower() in combined_boolean_filters
        and q
        or view_filter.lower() in combined_boolean_filters
        and q == ""
    ):
        raise APIQueryParamsError("Cannot use q parameter with boolean filters.")

    if (
        view_filter.lower() not in combined_boolean_filters
        and not q
        and view_filter.lower() not in combined_boolean_filters
        and q != ""
    ):
        raise APIQueryParamsError("Need q param for this parameter.")

    # requires sentence case
    sentence_case_fields = [
        "authorships.institutions.id",
        "authorships.author.id",
        "host_venue.display_name",
    ]

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
        field_underscore = "authorships__author__display_name"
    elif view_filter == "authorships.institutions.id":
        field_underscore = "authorships__institutions__display_name"
    elif view_filter == "host_venue.display_name":
        field_underscore = "host_venue__display_name"
    else:
        field_underscore = AUTOCOMPLETE_FILTER_DICT[view_filter].replace(".", "__")
    if view_filter in BOOLEAN_FILTERS:
        q = ""

    if q:
        if view_filter in sentence_case_fields:
            q = q.title().replace("Of", "of").strip()
        elif view_filter == "authorships.institutions.country_code":
            q = q.upper().strip()
        else:
            q = q.lower().strip()

        group_size = 50
        page_size = 10
        if view_filter == "authorships.institutions.country_code":
            country_codes = country_search(q)
            s = s.query("terms", **{field_underscore: country_codes})
        elif view_filter == "publication_year":
            min_year, max_year = set_year_min_max(q)
            kwargs = {field_underscore: {"gte": min_year, "lte": max_year}}
            s = s.query("range", **kwargs)
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
            _source=["authorships", "display_name", "host_venue"],
        )
        s.aggs.bucket("autocomplete_group", group)
        response = s.execute()
        for i in response.aggregations.autocomplete_group.buckets:
            id_key = set_key(i)

            if view_filter == "authorships.institutions.country_code":
                display_value = get_country_name(i.key)
            elif view_filter == "authorships.author.id":
                display_value = get_author_display_name(i)
            elif view_filter == "authorships.institutions.id":
                display_value = get_institution_display_name(i)
            elif view_filter == "host_venue.display_name":
                display_value = get_host_venue_display_name(i)
            else:
                display_value = id_key

            if str(display_value).lower().startswith(q.lower()):
                results.append(
                    {
                        "value": id_key,
                        "display_value": display_value,
                        "works_count": i.doc_count,
                    }
                )

    # add "zero" records
    zero_values = []
    if view_filter.lower() == "authorships.author.id":
        zero_values = get_top_authors(q)
    elif view_filter.lower() == "authorships.institutions.id":
        zero_values = get_top_institutions(q)
    elif view_filter.lower() == "host_venue.display_name":
        zero_values = get_top_venues(q)
    elif view_filter.lower() == "authorships.institutions.country_code":
        zero_values = get_top_countries(q)
    elif view_filter.lower() == "host_venue.publisher":
        zero_values = get_top_publishers(q)
    elif view_filter.lower() == "authorships.institutions.type":
        zero_values = get_top_institution_types(q)
    elif view_filter.lower() == "host_venue.license" and filter_params:
        zero_values = get_top_venue_licenses(q)
    elif view_filter.lower() == "host_venue.type" and filter_params:
        zero_values = get_top_venue_types(q)
    elif view_filter.lower() == "type" and filter_params:
        zero_values = get_top_works_types(q)
    elif view_filter.lower() == "open_access.oa_status" and filter_params:
        zero_values = get_top_works_oa_status(q)
    elif view_filter.lower() == "publication_year":
        zero_values = get_top_years(q)

    if (
        view_filter.lower() == "authorships.author.id"
        or view_filter.lower() == "authorships.institutions.id"
        or view_filter.lower() == "host_venue.display_name"
        or view_filter.lower() == "authorships.institutions.country_code"
        or view_filter.lower() == "host_venue.publisher"
        or view_filter.lower() == "authorships.institutions.type"
        or view_filter.lower() == "host_venue.license"
        or view_filter.lower() == "host_venue.type"
        or view_filter.lower() == "type"
        or view_filter.lower() == "open_access.oa_status"
        or view_filter.lower() == "publication_year"
    ):
        result_ids = [r["value"] for r in results]
        for item in zero_values:
            if item["id"] not in result_ids:
                results.append(
                    {
                        "value": item["id"],
                        "display_value": item["display_name"],
                        "works_count": 0,
                    }
                )

    if (
        view_filter.lower() == "is_paratext"
        or view_filter.lower() == "is_retracted"
        or view_filter.lower() == "open_access.is_oa"
    ):
        result_ids = [r["value"] for r in results]
        if "true" not in result_ids:
            results.append(
                {
                    "value": "true",
                    "display_value": "true",
                    "works_count": 0,
                }
            )
        if "false" not in result_ids:
            results.append(
                {
                    "value": "false",
                    "display_value": "false",
                    "works_count": 0,
                },
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
    else:
        results.append(
            {
                "value": "true",
                "display_value": "true",
                "works_count": 0,
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
    else:
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


def set_key(i):
    value = i.key
    if i.key == 1:
        value = "true"
    elif i.key == 0:
        value = "false"
    return value


def get_top_authors(q):
    s = Search(index=AUTHORS_INDEX)
    s = s.extra(size=10)
    s = s.sort("-works_count")
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    response = s.execute()
    authors = []
    for r in response:
        authors.append({"id": r.id, "display_name": r.display_name})
    return authors


def get_top_institutions(q):
    s = Search(index=INSTITUTIONS_INDEX)
    s = s.extra(size=10)
    s = s.sort("-works_count")
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    response = s.execute()
    institutions = []
    for r in response:
        institutions.append({"id": r.id, "display_name": r.display_name})
    return institutions


def get_top_venues(q):
    s = Search(index=VENUES_INDEX)
    s = s.extra(size=10)
    s = s.sort("-works_count")
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    response = s.execute()
    venues = []
    for r in response:
        venues.append({"id": r.id, "display_name": r.display_name})
    return venues


def get_top_countries(q):
    country_names = [n for n in iso3166.countries_by_name.keys()]
    matching_countries = []
    for country_name in country_names:
        if country_name.startswith(q.upper()):
            matching_countries.append(
                {
                    "id": iso3166.countries_by_name[country_name].alpha2,
                    "display_name": iso3166.countries_by_name[country_name].name,
                }
            )
    return matching_countries


def get_top_publishers(q):
    s = Search(index=VENUES_INDEX)
    s = s.query("prefix", publisher__lower=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="publisher.lower", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    publishers = []
    for i in response.aggregations.autocomplete_group.buckets:
        print(i.key)
        publishers.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return publishers


def get_top_institution_types(q):
    s = Search(index=INSTITUTIONS_INDEX)
    s = s.query("prefix", type=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="type", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    types = []
    for i in response.aggregations.autocomplete_group.buckets:
        types.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return types


def get_top_venue_licenses(q):
    s = Search(index=WORKS_INDEX)
    s = s.query("prefix", host_venue__license=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="host_venue.license", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    licenses = []
    for i in response.aggregations.autocomplete_group.buckets:
        licenses.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return licenses


def get_top_venue_types(q):
    s = Search(index=WORKS_INDEX)
    s = s.query("prefix", host_venue__type=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="host_venue.type", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    types = []
    for i in response.aggregations.autocomplete_group.buckets:
        types.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return types


def get_top_works_types(q):
    s = Search(index=WORKS_INDEX)
    s = s.query("prefix", type=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="type", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    types = []
    for i in response.aggregations.autocomplete_group.buckets:
        types.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return types


def get_top_works_oa_status(q):
    s = Search(index=WORKS_INDEX)
    s = s.query("prefix", open_access__oa_status=q.lower())
    s = s.params(preference="autocomplete_group_by")
    group = A("terms", field="open_access.oa_status", size=20)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    statuses = []
    for i in response.aggregations.autocomplete_group.buckets:
        statuses.append(
            {
                "id": i.key,
                "display_name": i.key,
            }
        )
    return statuses


def get_top_years(q):
    years = []
    today = date.today()
    current_year = today.year
    min_year = 1000
    max_year = current_year
    if str(q).startswith("1") and len(q) == 1:
        min_year = 1000
        max_year = 1999
    elif str(q).startswith("2") and len(q) == 1:
        min_year = 2000
        max_year = current_year
    elif len(q) == 2:
        min_year = int(q) * 100
        if current_year < int(q) * 100 + 99:
            max_year = current_year
        else:
            max_year = int(q) * 100 + 99
    elif len(q) == 3:
        min_year = int(q) * 10
        max_year = int(q) * 10 + 9
    elif len(q) == 4:
        min_year = int(q)
        max_year = int(q)
    i = 0
    for year in reversed(range(min_year, max_year + 1)):
        if i > 10:
            break
        years.append(
            {
                "id": year,
                "display_name": str(year),
            }
        )
        i = i + 1
    print(years)
    return years


def get_display_name(openalex_id):
    s = Search(index=AUTHORS_INDEX)
    s = s.filter("term", ids__openalex__lower=openalex_id)
    s = s.extra(size=1)
    s = s.source(["display_name"])
    response = s.execute()
    for r in response:
        return r.display_name


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
