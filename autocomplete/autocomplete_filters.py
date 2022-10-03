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
    "authorships.institutions.country_code": "authorships.institutions.country_code",
    "authorships.author.id": "authorships.author.display_name",
    "authorships.institutions.id": "authorships.institutions.display_name",
    "authorships.institutions.type": "authorships.institutions.type",
    "has_abstract": "abstract",
    "has_doi": "ids.doi",
    "has_ngrams": "fulltext",
    "is_paratext": "is_paratext",
    "is_retracted": "is_retracted",
    "open_access.is_oa": "open_access.is_oa",
    "host_venue.display_name": "host_venue.display_name",
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
    valid_filters = AUTOCOMPLETE_FILTER_DICT.keys()
    if view_filter not in valid_filters:
        raise APIQueryParamsError(
            f"The filter {view_filter} is not a valid filter. Current filters are: {', '.join(valid_filters)}"
        )

    # requires ID lookup through schema
    id_lookup_fields = [
        "authorships.institutions.id",
        "authorships.author.id",
        "host_venue.display_name",
    ]
    # requires sentence case
    sentence_case_fields = [
        "authorships.institutions.id",
        "authorships.author.id",
        "host_venue.display_name",
    ]

    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")
    group_size = 200
    page_size = 200

    s = Search(index=WORKS_INDEX)
    s = s.source(AUTOCOMPLETE_SOURCE)
    s = s.params(preference="autocomplete_group_by")

    # search
    if search and search != '""':
        s = full_search(index_name, s, search)

    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    combined_boolean_filters = BOOLEAN_FILTERS + HAS_FILTERS

    if view_filter.lower() in combined_boolean_filters and q:
        raise APIQueryParamsError("Cannot use q parameter with boolean filters.")
    elif view_filter.lower() not in combined_boolean_filters and not q:
        raise APIQueryParamsError(
            "q parameter is required for this autocomplete query."
        )

    # query
    field_underscore = AUTOCOMPLETE_FILTER_DICT[view_filter].replace(".", "__")
    if BOOLEAN_FILTERS:
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
        exists = A("filter", Q("exists", field=AUTOCOMPLETE_FILTER_DICT[view_filter]))
        not_exists = A(
            "filter", ~Q("exists", field=AUTOCOMPLETE_FILTER_DICT[view_filter])
        )
        s.aggs.bucket("exists", exists)
        s.aggs.bucket("not_exists", not_exists)
        response = s.execute()
        exists_count = response.aggregations.exists.doc_count
        not_exists_count = response.aggregations.not_exists.doc_count

        results.append(
            {
                "id": "true",
                "display_value": "true",
                "works_count": exists_count,
            }
        )
        results.append(
            {
                "id": "false",
                "display_value": "false",
                "works_count": not_exists_count,
            }
        )
    else:
        group = A("terms", field=AUTOCOMPLETE_FILTER_DICT[view_filter], size=group_size)
        s.aggs.bucket("autocomplete_group", group)
        response = s.execute()
        for i in response.aggregations.autocomplete_group.buckets:
            if view_filter in id_lookup_fields:
                id_key = None
            else:
                id_key = set_key(i)

            if view_filter == "authorships.institutions.country_code":
                display_value = get_country_name(i.key)
            else:
                display_value = set_key(i)

            check_field = (
                str(i.key).lower()
                if view_filter != "authorships.institutions.country_code"
                else display_value.lower()
            )

            if check_field.startswith(q.lower()):
                results.append(
                    {
                        "id": id_key,
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
