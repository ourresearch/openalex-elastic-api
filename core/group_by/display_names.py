import iso3166
import pycountry
from elasticsearch_dsl import Search, Q
from iso4217 import Currency

from core.utils import get_index_name_by_id, normalize_openalex_id
from settings import (
    DOMAINS_INDEX,
    FIELDS_INDEX,
    KEYWORDS_INDEX,
    LICENSES_INDEX,
    SUBFIELDS_INDEX
)


"""
Code to alter display names for group by fields.
"""


# Static mapping of SDG IDs to display names
# These 17 SDGs are permanent and never change
SDG_DISPLAY_NAMES = {
    "https://openalex.org/sdgs/1": "No poverty",
    "https://openalex.org/sdgs/2": "Zero hunger",
    "https://openalex.org/sdgs/3": "Good health and well-being",
    "https://openalex.org/sdgs/4": "Quality education",
    "https://openalex.org/sdgs/5": "Gender equality",
    "https://openalex.org/sdgs/6": "Clean water and sanitation",
    "https://openalex.org/sdgs/7": "Affordable and clean energy",
    "https://openalex.org/sdgs/8": "Decent work and economic growth",
    "https://openalex.org/sdgs/9": "Industry, innovation and infrastructure",
    "https://openalex.org/sdgs/10": "Reduced inequalities",
    "https://openalex.org/sdgs/11": "Sustainable cities and communities",
    "https://openalex.org/sdgs/12": "Responsible consumption and production",
    "https://openalex.org/sdgs/13": "Climate action",
    "https://openalex.org/sdgs/14": "Life below water",
    "https://openalex.org/sdgs/15": "Life on land",
    "https://openalex.org/sdgs/16": "Peace, justice, and strong institutions",
    "https://openalex.org/sdgs/17": "Partnerships for the goals",
    # Also support metadata.un.org URLs which appear in v2
    "https://metadata.un.org/sdg/1": "No poverty",
    "https://metadata.un.org/sdg/2": "Zero hunger",
    "https://metadata.un.org/sdg/3": "Good health and well-being",
    "https://metadata.un.org/sdg/4": "Quality education",
    "https://metadata.un.org/sdg/5": "Gender equality",
    "https://metadata.un.org/sdg/6": "Clean water and sanitation",
    "https://metadata.un.org/sdg/7": "Affordable and clean energy",
    "https://metadata.un.org/sdg/8": "Decent work and economic growth",
    "https://metadata.un.org/sdg/9": "Industry, innovation and infrastructure",
    "https://metadata.un.org/sdg/10": "Reduced inequalities",
    "https://metadata.un.org/sdg/11": "Sustainable cities and communities",
    "https://metadata.un.org/sdg/12": "Responsible consumption and production",
    "https://metadata.un.org/sdg/13": "Climate action",
    "https://metadata.un.org/sdg/14": "Life below water",
    "https://metadata.un.org/sdg/15": "Life on land",
    "https://metadata.un.org/sdg/16": "Peace, justice, and strong institutions",
    "https://metadata.un.org/sdg/17": "Partnerships for the goals",
}


def get_id_display_names(ids, connection='default'):
    """Takes a list of ids and returns a dict with id[display_name]"""
    if not ids or (ids[0] == "unknown" and len(ids) == 1):
        return None

    if ids[0] == "unknown" and len(ids) > 1:
        index_name = get_index_name_by_id(ids[1], connection=connection)
    else:
        index_name = get_index_name_by_id(ids[0], connection=connection)
    s = Search(index=index_name, using=connection)
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


def get_display_names_host_organization(ids, connection='default'):
    """Host organization is a special case because it can be an institution or a publisher."""
    institution_ids = []
    publisher_ids = []
    for openalex_id in ids:
        clean_id = normalize_openalex_id(openalex_id)
        if clean_id and clean_id.startswith("I"):
            institution_ids.append(openalex_id)
        elif clean_id and clean_id.startswith("P"):
            publisher_ids.append(openalex_id)
    institution_names = get_id_display_names(institution_ids, connection)
    publisher_names = get_id_display_names(publisher_ids, connection)

    # merge the two dictionaries
    results = {}
    if institution_names:
        results.update(institution_names)
    if publisher_names:
        results.update(publisher_names)
    return results


def get_display_names_sdgs(ids, connection='default'):
    """
    Returns display names for SDG IDs using the in-memory cache/static mapping.
    No index queries needed since there are only 17 SDGs that never change.
    Multiple queries to works index would be needed if we used the SDG IDs in the works index.
    """
    results = {}
    for sdg_id in ids:
        if sdg_id in SDG_DISPLAY_NAMES:
            results[sdg_id] = SDG_DISPLAY_NAMES[sdg_id]
    return results


def get_display_names_keywords_licenses_topics(ids, connection='default'):
    if not ids or (ids[0] == "unknown" and len(ids) == 1):
        return None

    index = f"{FIELDS_INDEX},{SUBFIELDS_INDEX},{DOMAINS_INDEX},{KEYWORDS_INDEX},{LICENSES_INDEX}"
    s = Search(index=index, using=connection)
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


def get_display_name_mapping(keys, group_by, connection='default'):
    display_name_functions = {
        "host_organization": get_display_names_host_organization,
        "host_organization_lineage": get_display_names_host_organization,
        "domain.id": get_display_names_keywords_licenses_topics,
        "subfield.id": get_display_names_keywords_licenses_topics,
        "subfields.id": get_display_names_keywords_licenses_topics,
        "field.id": get_display_names_keywords_licenses_topics,
        "fields.id": get_display_names_keywords_licenses_topics,
        "keywords.id": get_display_names_keywords_licenses_topics,
        "sustainable_development_goals.id": get_display_names_sdgs,
        "license": get_display_names_keywords_licenses_topics,
        "license_id": get_display_names_keywords_licenses_topics,
    }

    for key, func in display_name_functions.items():
        if group_by.endswith(key):
            return func(keys, connection)

    return get_id_display_names(keys, connection)


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
        "license",
        "license_id",
    )
    exact_matches = (
        "authorships.institutions.lineage",
        "last_known_institutions.lineage",
    )
    return group_by.endswith(endings) or group_by in exact_matches
