import iso3166
from elasticsearch_dsl import Q


def filter_group_by(field, group_by, q, s):
    """Reduce records that will be grouped based on q param."""
    autocomplete_field_mapping = {
        "ancestors.id": "ancestors__display_name__autocomplete",
        "authorships.institutions.id": "authorships__institutions__display_name__autocomplete",
        "authorships.author.id": "authorships__author__display_name__autocomplete",
        "best_oa_location.source.id": "best_oa_location__source__display_name__autocomplete",
        "concept.id": "concepts__display_name__autocomplete",
        "concepts.id": "concepts__display_name__autocomplete",
        "corresponding_author_ids": "authorships__author__display_name__autocomplete",
        "corresponding_institution_ids": "authorships__institutions__display_name__autocomplete",
        "keywords.id": "keywords__display_name",
        "journal": "locations__source__display_name__autocomplete",
        "last_known_institutions.id": "last_known_institutions__display_name__autocomplete",
        "locations.source.id": "locations__source__display_name__autocomplete",
        "locations.source.publisher_lineage": "locations__source__host_organization_lineage_names__autocomplete",
        "primary_location.source.id": "primary_location__source__display_name__autocomplete",
        "publisher": "publisher__autocomplete",
        "repository": "locations__source__display_name__autocomplete",
    }
    if autocomplete_field_mapping.get(group_by):
        slop = get_slop(group_by)
        field = autocomplete_field_mapping[group_by]
        query = Q("match_phrase_prefix", **{field: {"query": q, "slop": slop}})
        s = s.query(query)
    elif "country_code" in group_by:
        country_codes = country_search(q)
        s = s.query("terms", **{field.es_field(): country_codes})
    elif group_by == "publication_year":
        min_year, max_year = set_year_min_max(q)
        kwargs = {"publication_year": {"gte": min_year, "lte": max_year}}
        s = s.query("range", **kwargs)
    elif (
        "author" in group_by
        or group_by == "grants.funder"
        or group_by.endswith("host_institution_lineage")
        or group_by.endswith("host_organization")
        or group_by.endswith("host_organization_lineage")
        or "institution" in group_by
        or group_by == "lineage"
        or group_by.endswith("publisher_lineage")
        or group_by == "repository"
        or group_by == "language"
        or group_by == "sustainable_development_goals.id"
    ):
        return s
    else:
        s = s.query("prefix", **{field.es_field(): q.lower()})
    return s


def get_slop(group_by):
    if "author.id" in group_by:
        # allows us to ignore middle initials in names
        slop = 1
    else:
        slop = 0
    return slop


def country_search(q):
    country_names = [n for n in iso3166.countries_by_name.keys()]
    matching_country_codes = []
    for country_name in country_names:
        if country_name.startswith(q.upper()):
            matching_country_codes.append(
                iso3166.countries_by_name[country_name].alpha2
            )
    return matching_country_codes


def set_year_min_max(q):
    min_year = 1000
    max_year = 3000
    if str(q).startswith("1") and len(q) == 1:
        min_year = 1000
        max_year = 1999
    elif str(q).startswith("2") and len(q) == 1:
        min_year = 2000
        max_year = 2999
    elif len(q) == 2:
        min_year = int(q) * 100
        max_year = int(q) * 100 + 99
    elif len(q) == 3:
        min_year = int(q) * 10
        max_year = int(q) * 10 + 9
    elif len(q) == 4:
        min_year = int(q)
        max_year = int(q)
    return min_year, max_year
