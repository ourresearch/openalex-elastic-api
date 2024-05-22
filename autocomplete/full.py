from collections import OrderedDict

from elasticsearch_dsl import Q

import settings
from autocomplete.shared import is_year_query


def get_indices():
    entities_to_indeces = {
        "author": settings.AUTHORS_INDEX,
        "concept": settings.CONCEPTS_INDEX,
        "countries": settings.COUNTRIES_INDEX,
        "institution": settings.INSTITUTIONS_INDEX,
        "funder": settings.FUNDERS_INDEX,
        "keyword": settings.KEYWORDS_INDEX,
        "language": settings.LANGUAGES_INDEX,
        "license": settings.LICENSES_INDEX,
        "publisher": settings.PUBLISHERS_INDEX,
        "sdgs": settings.SDGS_INDEX,
        "source": settings.SOURCES_INDEX,
        "topic": settings.TOPICS_INDEX,
        "work": settings.WORKS_INDEX,
        "work_type": settings.WORK_TYPES_INDEX,
    }
    return entities_to_indeces


def create_filter_result(filter_key, return_value):
    return OrderedDict(
        {
            "id": return_value,
            "display_name": return_value,
            "cited_by_count": 0,
            "entity_type": "filter",
            "external_id": None,
            "filter_key": filter_key,
        }
    )


def get_filter_results(q):
    if not q:
        return []

    filter_results = []

    # special cases
    if is_year_query(q):
        filter_results.append(create_filter_result("publication_year", q))

    # general
    filters = [
        {
            "name": "has_abstract",
            "matches": [
                {"query": "has abstract", "min_len": 5, "value": True},
                {"query": "no abstract", "min_len": 5, "value": False},
            ],
        },
        {
            "name": "has_doi",
            "matches": [
                {"query": "has doi", "min_len": 5, "value": True},
                {"query": "no doi", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "has_fulltext",
            "matches": [
                {"query": "has fulltext", "min_len": 5, "value": True},
                {"query": "no fulltext", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "has_orcid",
            "matches": [
                {"query": "has orcid", "min_len": 5, "value": True},
                {"query": "no orcid", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "has_pmid",
            "matches": [
                {"query": "has pmid", "min_len": 5, "value": True},
                {"query": "no pmid", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "has_pmcid",
            "matches": [
                {"query": "has pmcid", "min_len": 5, "value": True},
                {"query": "no pmcid", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "has_pdf_url",
            "matches": [
                {"query": "has pdf url", "min_len": 5, "value": True},
                {"query": "no pdf url", "min_len": 4, "value": False},
            ],
        },
        {
            "name": "is_paratext",
            "matches": [
                {"query": "paratext", "min_len": 3, "value": True},
                {"query": "not paratext", "min_len": 6, "value": False},
                {"query": "no paratext", "min_len": 5, "value": False},
            ],
        },
        {
            "name": "is_retracted",
            "matches": [
                {"query": "retracted", "min_len": 3, "value": True},
                {"query": "not retracted", "min_len": 5, "value": False},
            ],
        },
        {
            "name": "open_access.is_oa",
            "matches": [
                {"query": "open access", "min_len": 3, "value": True},
                {"query": "closed access", "min_len": 5, "value": False},
                {"query": "not open access", "min_len": 6, "value": False},
            ],
        },
    ]

    # oa statuses
    statuses = [
        "closed",
        "bronze",
        "hybrid",
        "green",
        "gold",
    ]
    for status in statuses:
        if len(q) >= 3 and status.startswith(q.lower()):
            filter_results.append(create_filter_result("oa_status", status))

    for filter in filters:
        for match in filter["matches"]:
            if len(q) >= match["min_len"] and match["query"].startswith(q.lower()):
                filter_results.append(
                    create_filter_result(filter["name"], match["value"])
                )

    return filter_results


def build_full_search_query(q, s, sort):
    s = s.filter(
        Q("match_phrase_prefix", display_name__autocomplete=q)
        | Q("match_phrase_prefix", alternate_titles__autocomplete=q)
        | Q("match_phrase_prefix", abbreviated_title__autocomplete=q)
        | Q("match_phrase_prefix", display_name_acronyms__autocomplete=q)
        | Q("match_phrase_prefix", display_name_alternatives__autocomplete=q)
        | Q("match_phrase_prefix", description__autocomplete=q)
    )
    # do not show repository
    s = s.exclude("term", type="repository")
    s = s.sort(sort)
    return s
