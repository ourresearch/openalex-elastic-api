from collections import OrderedDict

from elasticsearch_dsl import Q

import settings
from autocomplete.shared import is_year_query


def get_indices_and_boosts():
    entities_to_indeces = {
        "author": settings.AUTHORS_INDEX,
        "concept": settings.CONCEPTS_INDEX,
        "countries": "countries",
        "institution": settings.INSTITUTIONS_INDEX,
        "funder": settings.FUNDERS_INDEX,
        "publisher": settings.PUBLISHERS_INDEX,
        "source": settings.SOURCES_INDEX,
        "work": settings.WORKS_INDEX,
        "work_type": "work-type",
    }
    index_boosts = {
        settings.AUTHORS_INDEX: 3,
        settings.CONCEPTS_INDEX: 0.35,
        settings.FUNDERS_INDEX: 0.5,
        settings.INSTITUTIONS_INDEX: 2,
        settings.PUBLISHERS_INDEX: 0.15,
        settings.SOURCES_INDEX: 0.5,
        settings.WORKS_INDEX: 0.75,
    }
    return entities_to_indeces, index_boosts


def create_short_circuit_result(filter_key, return_value):
    result = OrderedDict()
    result["meta"] = {
        "count": 1,
        "db_response_time_ms": 0,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = [
        OrderedDict(
            {
                "id": return_value,
                "display_name": None,
                "cited_by_count": 0,
                "entity_type": "filter",
                "external_id": None,
                "filter_key": filter_key,
            }
        )
    ]
    return result


def short_circuit_response(q):
    result = None
    is_oa_filter = "open_access.is_oa"
    year_filter = "publication_year"

    # open access
    if q and len(q) > 3 and "open access".startswith(q.lower()):
        result = create_short_circuit_result(is_oa_filter, True)

    # closed access
    if q and len(q) > 4 and "closed access".startswith(q.lower()):
        result = create_short_circuit_result(is_oa_filter, False)
    elif q and len(q) > 5 and "not open access".startswith(q.lower()):
        result = create_short_circuit_result(is_oa_filter, False)

    # year
    if q and is_year_query(q):
        result = create_short_circuit_result(year_filter, q)
    return result


def build_full_search_query(q, s):
    s = s.query(
        Q("match_phrase_prefix", display_name__autocomplete=q)
        | Q("match_phrase_prefix", alternate_titles__autocomplete=q)
        | Q("match_phrase_prefix", abbreviated_title__autocomplete=q)
        | Q("match_phrase_prefix", display_name_acronyms__autocomplete=q)
        | Q("match_phrase_prefix", display_name_alternatives__autocomplete=q)
    )
    # do not show repository
    s = s.exclude("term", type="repository")
    # boost by cited_by_count
    s = s.query(
        "function_score",
        functions=[
            {
                "field_value_factor": {
                    "field": "cited_by_count",
                    "factor": 1,
                    "modifier": "sqrt",
                    "missing": 1,
                }
            }
        ],
        boost_mode="multiply",
    )
    return s
