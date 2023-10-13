from elasticsearch_dsl import Search, Q, MultiSearch

from core.utils import get_index_name_by_id, normalize_openalex_id
from settings import WORKS_INDEX


def get_display_names(ids):
    """Takes a list of ids and returns a dict with id[display_name]"""
    if not ids or (ids[0] == "unknown" and len(ids) == 1):
        return None

    if ids[0] == "unknown" and len(ids) > 1:
        index_name = get_index_name_by_id(ids[1])
    else:
        index_name = get_index_name_by_id(ids[0])
    s = Search(index=index_name)
    s = s.extra(size=500)
    s = s.source(["id", "display_name"])

    results = {}
    or_queries = []
    for openalex_id in ids:
        or_queries.append(Q("term", id=openalex_id))
    combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
    s = s.query(combined_or_query)
    response = s.execute()

    for item in response:
        results[item.id] = item.display_name
    return results


def get_display_names_host_organization(ids):
    """Host organization is a special case because it can be an institution or a publisher."""
    institution_ids = []
    publisher_ids = []
    for openalex_id in ids:
        clean_id = normalize_openalex_id(openalex_id)
        if clean_id and clean_id.startswith("I"):
            institution_ids.append(openalex_id)
        elif clean_id and clean_id.startswith("P"):
            publisher_ids.append(openalex_id)
    institution_names = get_display_names(institution_ids)
    publisher_names = get_display_names(publisher_ids)

    # merge the two dictionaries
    results = {}
    if institution_names:
        results.update(institution_names)
    if publisher_names:
        results.update(publisher_names)
    return results


def get_display_names_award_ids(ids):
    results = {}
    ms = MultiSearch(index=WORKS_INDEX)
    for award_id in ids:
        s = Search()
        s = s.filter("term", grants__award_id__keyword=award_id)
        s = s.source(["grants"])
        ms = ms.add(s)
    responses = ms.execute()
    for response in responses:
        # get count for each query
        count = response.hits.total.value
        for item in response:
            for grant in item.grants:
                if grant.award_id in ids:
                    results[
                        grant.award_id
                    ] = f"{grant.funder_display_name} ({grant.award_id})"
    return results


def get_display_names_sdgs(ids):
    # kind of hacky. consider redoing
    results = {}
    ms = MultiSearch(index=WORKS_INDEX)
    for sdg_id in ids:
        s = Search()
        s = s.filter("term", sustainable_development_goals__id__keyword=sdg_id)
        s = s.source(
            [
                "sustainable_development_goals.id",
                "sustainable_development_goals.display_name",
            ]
        )
        ms = ms.add(s)
    responses = ms.execute()
    for sdg_id in ids:
        for response in responses:
            for item in response:
                if sdg_id in results:
                    break
                for sdg in item.sustainable_development_goals:
                    if sdg.id == sdg_id:
                        results[sdg.id] = sdg.display_name
    return results
