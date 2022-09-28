from collections import OrderedDict

from elasticsearch_dsl import Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE, get_preference
from autocomplete.validate import validate_entity_autocomplete_params
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import full_search
from core.utils import map_filter_params
from settings import (AUTHORS_INDEX, CONCEPTS_INDEX, INSTITUTIONS_INDEX,
                      VENUES_INDEX, WORKS_INDEX)


def autocomplete_filter(fields_dict, index_name, request):
    entities_to_indeces = {
        "author": AUTHORS_INDEX,
        "concept": CONCEPTS_INDEX,
        "institution": INSTITUTIONS_INDEX,
        "venue": VENUES_INDEX,
        "work": WORKS_INDEX,
    }
    full_index = ",".join(entities_to_indeces.values())
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")
    if not q:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use autocomplete. Example: {request.url_rule}?q=my search"
        )

    s = Search(index=full_index)

    # # search
    if search and search != '""':
        s = full_search(index_name, s, search)

    # filters
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    # autocomplete
    s = s.query("match_phrase_prefix", display_name__autocomplete=q)
    s = s.sort("-cited_by_count")
    s = s.source(AUTOCOMPLETE_SOURCE)
    preference = get_preference(q)
    s = s.params(preference=preference)

    response = s.execute()

    results = []
    authors = {"key": "author.id", "values": []}
    concepts = {"key": "concepts.id", "values": []}
    institutions = {"key": "institution.id", "values": []}
    venues = {"key": "host_venue.id", "values": []}
    order = []
    order_key = {
        "author": authors,
        "concept": concepts,
        "institution": institutions,
        "venue": venues,
    }

    for record in response:
        if "author" in record.meta.index:
            authors["values"].append(
                {
                    "value": record.id,
                    "display_value": record.display_name,
                    "cited_by_count": record.cited_by_count,
                }
            )
            order.append("author")
        if "concept" in record.meta.index:
            concepts["values"].append(
                {
                    "value": record.id,
                    "display_value": record.display_name,
                    "cited_by_count": record.cited_by_count,
                }
            )
            order.append("concept")
        if "institution" in record.meta.index:
            institutions["values"].append(
                {
                    "value": record.id,
                    "display_value": record.display_name,
                    "cited_by_count": record.cited_by_count,
                }
            )
            order.append("institution")
        if "venue" in record.meta.index:
            venues["values"].append(
                {
                    "value": record.id,
                    "display_value": record.display_name,
                    "cited_by_count": record.cited_by_count,
                }
            )
            order.append("venue")

    # order
    new_order = []
    for item in order:
        if item not in new_order:
            new_order.append(item)
    for key in order_key.keys():
        if key not in new_order:
            new_order.append(key)
    for item in new_order:
        results.append(order_key[item])

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["filters"] = results
    return result
