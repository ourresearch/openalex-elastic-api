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


def autocomplete_filter(view_filter, fields_dict, index_name, request):
    filter_dict = {
        "authorships.institutions.id": "authorships.institutions.display_name",
        "institution.id": "authorships.institutions.display_name",
        "author.id": "authorships.author.display_name"
    }
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    unfiltered = request.args.get("unfiltered")
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
    field_underscore = filter_dict[view_filter].replace(".", "__")
    s = s.query("prefix", **{field_underscore: q.title().replace("Of", "of")})

    # group
    group = A(
        "terms", field=filter_dict[view_filter], size=50
    )
    s.aggs.bucket("autocomplete_group", group)
    response = s.execute()
    results = []
    for i in response.aggregations.autocomplete_group.buckets:
        if unfiltered:
            results.append(
                {
                    "id": None,
                    "display_value": i.key,
                    "works_count": i.doc_count,
                }
            )
        else:
            if q.lower() in i.key.lower():
                results.append(
                    {
                        "id": None,
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
