from collections import OrderedDict

import iso3166
from elasticsearch_dsl import A, Search

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
    "host_venue.display_name": "host_venue.display_name",
    "host_venue.license": "host_venue.license",
    "host_venue.publisher": "host_venue.publisher.lower",
    "host_venue.type": "host_venue.type",
    "open_access.oa_status": "open_access.oa_status",
    "publication_year": "publication_year",
    "type": "type",
}


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
    if not q:
        result = OrderedDict()
        result["meta"] = {
            "count": 0,
            "db_response_time_ms": 1,
            "page": 1,
            "per_page": 10,
        }
        result["filters"] = []
        return result

    s = Search(index=WORKS_INDEX)
    s = s.source(AUTOCOMPLETE_SOURCE)
    s = s.params(preference="autocomplete_group_by")

    # search
    if search and search != '""':
        s = full_search(index_name, s, search)

    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    # query
    field_underscore = AUTOCOMPLETE_FILTER_DICT[view_filter].replace(".", "__")
    if view_filter in sentence_case_fields:
        q = q.title().replace("Of", "of").strip()
    elif view_filter == "authorships.institutions.country_code":
        q = q.upper().strip()
    else:
        q = q.lower().strip()

    if view_filter == "authorships.institutions.country_code":
        country_codes = country_search(q)
        s = s.query("terms", **{field_underscore: country_codes})
    elif view_filter == "publication_year":
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
        kwargs = {field_underscore: {"gte": min_year, "lte": max_year}}
        s = s.query("range", **kwargs)
    else:
        s = s.query("prefix", **{field_underscore: q})

    # group
    group = A("terms", field=AUTOCOMPLETE_FILTER_DICT[view_filter], size=50)
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    results = []
    for i in response.aggregations.autocomplete_group.buckets:
        if view_filter in id_lookup_fields:
            id_key = None
        else:
            id_key = i.key

        if view_filter == "authorships.institutions.country_code":
            display_value = get_country_name(i.key)
        else:
            display_value = str(i.key)

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
        "per_page": 10,
    }
    result["filters"] = results[:10]
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
