from collections import OrderedDict

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
    "authorships.author.id": "authorships.author.display_name",
    "authorships.institutions.id": "authorships.institutions.display_name",
    "authorships.institutions.type": "authorships.institutions.type",
    "host_venue.display_name": "host_venue.display_name",
    "host_venue.publisher": "host_venue.publisher.lower",
    "host_venue.type": "host_venue.type",
    "open_access.oa_status": "open_access.oa_status",
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
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

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
    else:
        q = q.lower().strip()
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
        if q.lower() in i.key.lower():
            results.append(
                {
                    "id": id_key,
                    "display_value": i.key,
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
