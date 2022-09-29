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
    s = s.params(preference="institution_group_by")

    # search
    if search and search != '""':
        s = full_search(index_name, s, search)

    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    # institution
    s = s.query("prefix", authorships__institutions__display_name=q.title().replace("Of", "of"))
    institution_group = A(
        "terms", field="authorships.institutions.display_name", size=50
    )
    s.aggs.bucket("institution", institution_group)
    response = s.execute()
    results = []
    for i in response.aggregations.institution.buckets:
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
