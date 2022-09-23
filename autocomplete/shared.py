from collections import OrderedDict

from elasticsearch_dsl import Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE, get_preference
from autocomplete.validate import validate_entity_autocomplete_params
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import full_search
from core.utils import map_filter_params


def single_entity_autocomplete(fields_dict, index_name, request):
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")

    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    s = Search(index=index_name)
    # search
    if search and search != '""':
        s = full_search(index_name, s, search)
    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    s = s.sort("-cited_by_count")
    s = s.source(AUTOCOMPLETE_SOURCE)
    preference = get_preference(q)
    s = s.params(preference=preference)
    response = s.execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = response
    return result
