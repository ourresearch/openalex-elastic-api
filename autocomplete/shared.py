from collections import OrderedDict

from elasticsearch_dsl import Search

from autocomplete.utils import strip_punctuation
from core.exceptions import APIQueryParamsError


def single_entity_autocomplete(index_name, request):
    q = request.args.get("q")
    q = strip_punctuation(q) if q else None
    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    s = Search(index=index_name)
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    s = s.sort("-cited_by_count")
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
