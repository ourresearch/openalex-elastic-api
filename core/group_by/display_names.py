import iso3166
import pycountry
from elasticsearch_dsl import Search, Q, MultiSearch
from iso4217 import Currency

from core.utils import get_index_name_by_id, normalize_openalex_id
from settings import DOMAINS_INDEX, FIELDS_INDEX, SUBFIELDS_INDEX, WORKS_INDEX


"""
Code to alter display names for group by fields.
"""


def get_id_display_names(ids):
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
    institution_names = get_id_display_names(institution_ids)
    publisher_names = get_id_display_names(publisher_ids)

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
        s = s.filter("term", sustainable_development_goals__id__lower=sdg_id)
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


def get_display_names_topics(ids):
    if not ids or (ids[0] == "unknown" and len(ids) == 1):
        return None

    index = f"{FIELDS_INDEX},{SUBFIELDS_INDEX},{DOMAINS_INDEX}"
    s = Search(index=index)
    s = s.extra(size=500)
    s = s.source(["id", "display_name"])

    results = {}
    or_queries = []
    for integer_id in ids:
        or_queries.append(Q("term", id=integer_id))
    combined_or_query = Q("bool", should=or_queries, minimum_should_match=1)
    s = s.query(combined_or_query)
    response = s.execute()

    for item in response:
        results[item.id] = item.display_name
    return results


def get_key_display_name(b, group_by):
    if b.key == "unknown":
        return "unknown"

    if group_by.endswith("country_code") or group_by.endswith("countries"):
        try:
            country = iso3166.countries.get(b.key.lower())
            return country.name if country else None
        except KeyError:
            return None

    if group_by == "apc_payment.provenance":
        if b.key == "doaj":
            return "Directory of Open Access Journals (DOAJ) at https://doaj.org"
        if b.key == "openapc":
            return "OpenAPC at https://openapc.net"

    if group_by.endswith("currency"):
        return Currency(b.key).currency_name

    if group_by == "language":
        if b.key.lower() == "zh-cn":
            return "Chinese"
        language = pycountry.languages.get(alpha_2=b.key.lower())
        return language.name if language else None

    # Default case
    return b.key if "key_as_string" not in b else b.key_as_string


def get_display_name_mapping(keys, group_by):
    display_name_functions = {
        "host_organization": get_display_names_host_organization,
        "host_organization_lineage": get_display_names_host_organization,
        "domain.id": get_display_names_topics,
        "subfield.id": get_display_names_topics,
        "subfields.id": get_display_names_topics,
        "field.id": get_display_names_topics,
        "fields.id": get_display_names_topics,
        "grants.award_id": get_display_names_award_ids,
        "sustainable_development_goals.id": get_display_names_sdgs,
    }

    for key, func in display_name_functions.items():
        if group_by.endswith(key):
            return func(keys)

    return get_id_display_names(keys)


def requires_display_name_conversion(group_by):
    endings = (
        ".id",
        "host_organization",
        "repository",
        "journal",
        "host_organization_lineage",
        "host_institution_lineage",
        "publisher_lineage",
        "ids",
    )
    exact_matches = (
        "authorships.institutions.lineage",
        "grants.award_id",
        "grants.funder",
        "last_known_institution.lineage",
    )
    return group_by.endswith(endings) or group_by in exact_matches
