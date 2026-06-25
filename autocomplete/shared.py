from collections import OrderedDict

from elasticsearch_dsl import Q, Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE
from autocomplete.validate import validate_entity_autocomplete_params
from core.filter import filter_records
from core.search import full_search_query
from core.utils import map_filter_params
from core.preference import clean_preference
from ids import utils as id_utils


def single_entity_autocomplete(fields_dict, index_name, request, connection='default'):
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")

    s = Search(index=index_name, using=connection)
    canonical_id_found = False

    # Exclude deleted author ID for author indexes
    if "author" in index_name:
        s = s.exclude("term", ids__openalex="https://openalex.org/A5317838346")

    if q:
        # canonical id match
        s, canonical_id_found = search_canonical_id_single(index_name, s, q)

    if not canonical_id_found:
        if search and search != '""':
            search_query = full_search_query(index_name, search)
            s = s.query(search_query)

        # filters
        if filter_params:
            s = filter_records(fields_dict, filter_params, s)

        # Popularity field used both to rank q-matches and as the sort tiebreaker.
        popularity_field = (
            "cited_by_count" if index_name.startswith("work") else "works_count"
        )

        if q:
            # Build two queries per entity type:
            #   autocomplete_query — the full candidate selector (display_name plus
            #     every alternate field), unchanged from before.
            #   primary_query — the "primary identifier" fields a user recognises the
            #     entity by: its display_name plus identifier-style fields (acronyms,
            #     abbreviated titles). Used to give those matches a higher tier than
            #     name-variant / description matches below.
            if index_name.startswith("author"):
                primary_query = Q("match_phrase_prefix", display_name__autocomplete=q)
                autocomplete_query = primary_query | Q(
                    "match_phrase_prefix", display_name_alternatives__autocomplete=q
                )
            elif index_name.startswith("institution"):
                primary_query = Q(
                    "match_phrase_prefix", display_name__autocomplete=q
                ) | Q("match_phrase_prefix", display_name_acronyms__autocomplete=q)
                autocomplete_query = primary_query | Q(
                    "match_phrase_prefix", display_name_alternatives__autocomplete=q
                )
            elif index_name.startswith("source"):
                # A source's alternate_titles are curated (real journal acronyms
                # like "JACS"), so all of its match fields count as primary.
                primary_query = (
                    Q("match_phrase_prefix", display_name__autocomplete=q)
                    | Q("match_phrase_prefix", abbreviated_title__autocomplete=q)
                    | Q("match_phrase_prefix", alternate_titles__autocomplete=q)
                )
                autocomplete_query = primary_query
            elif index_name.startswith("topic"):
                primary_query = Q("match_phrase_prefix", display_name__autocomplete=q)
                autocomplete_query = (
                    primary_query
                    | Q("match_phrase_prefix", description__autocomplete=q)
                    | Q("match_phrase_prefix", keywords__autocomplete=q)
                )
            else:
                primary_query = Q("match_phrase_prefix", display_name__autocomplete=q)
                autocomplete_query = primary_query

            # Rank the suggestions in three popularity-ordered tiers so the
            # canonical high-works entity floats to the top (e.g. "nature" -> the
            # journal Nature, "florida" -> University of Florida, "mit" -> MIT via
            # its acronym). autocomplete_query only SELECTS candidates;
            # boost_mode="replace" discards its noisy match_phrase_prefix relevance,
            # and we score each doc as tier_weight + log1p(popularity), so the order
            # is:
            #   1. exact display_name match (case-insensitive),
            #   2. match on a primary identifier field (display_name / acronym /
            #      abbreviated title),
            #   3. match only on another alternate field (name variants, topic
            #      description/keywords),
            # and WITHIN each tier by popularity (works_count, or cited_by_count for
            # works). The exact filter is case-insensitive because users type
            # lowercase. Keeping identifier matches above name-variant matches stops a
            # high-works entity that merely has an alternate name containing the query
            # (e.g. an author whose alt-name contains "jas") from displacing entities
            # whose visible name actually matches. See oxjob #516.
            ranked_query = Q(
                "function_score",
                query=autocomplete_query,
                functions=[
                    {
                        "filter": Q(
                            "term",
                            display_name__keyword={
                                "value": q,
                                "case_insensitive": True,
                            },
                        ),
                        "weight": 2000000,
                    },
                    {
                        "filter": primary_query,
                        "weight": 1000000,
                    },
                    {
                        "field_value_factor": {
                            "field": popularity_field,
                            "modifier": "log1p",
                            "missing": 0,
                        }
                    },
                ],
                score_mode="sum",
                boost_mode="replace",
            )

            s = s.query(ranked_query)

        s = s.sort("_score", f"-{popularity_field}")

        s = s.source(AUTOCOMPLETE_SOURCE)
        preference = clean_preference(q)
        s = s.params(preference=preference)

    print(s.to_dict())
    response = s.params(timeout='5s').execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = response
    return result


def search_canonical_id_single(index_name, s, q):
    canonical_id_found = False
    if (
        (index_name.startswith("author") and id_utils.is_author_openalex_id(q))
        or (index_name.startswith("concept") and id_utils.is_concept_openalex_id(q))
        or (
            index_name.startswith("institution")
            and id_utils.is_institution_openalex_id(q)
        )
        or (index_name.startswith("source") and id_utils.is_source_openalex_id(q))
        or (index_name.startswith("work") and id_utils.is_work_openalex_id(q))
    ):
        s = filter_openalex_id(q, s)
        canonical_id_found = True
    elif index_name.startswith("author") and id_utils.is_orcid(q):
        normalized_id = id_utils.normalize_orcid(q)
        orcid_id = f"https://orcid.org/{normalized_id}"
        s = s.filter("term", ids__orcid=orcid_id)
        canonical_id_found = True
    elif index_name.startswith("concept") and id_utils.is_wikidata(q):
        normalized_id = id_utils.normalize_wikidata(q)
        wikidata_id = f"https://www.wikidata.org/wiki/{normalized_id}"
        s = s.filter("term", ids__wikidata=wikidata_id)
        canonical_id_found = True
    elif index_name.startswith("institution") and id_utils.is_ror(q):
        normalized_id = id_utils.normalize_ror(q)
        ror_id = f"https://ror.org/{normalized_id}"
        s = s.filter("term", ror=ror_id)
        canonical_id_found = True
    elif index_name.startswith("source") and id_utils.is_issn(q):
        normalized_id = id_utils.normalize_issn(q)
        s = s.filter("term", ids__issn__lower=normalized_id)
        canonical_id_found = True
    elif index_name.startswith("work") and id_utils.is_doi(q):
        normalized_id = id_utils.normalize_doi(q)
        doi = f"https://doi.org/{normalized_id}"
        s = s.filter("term", ids__doi=doi)
        canonical_id_found = True
    return s, canonical_id_found


def search_canonical_id_full(s, q):
    canonical_id_found = False
    if id_utils.is_openalex_id(q):
        s = filter_openalex_id(q, s)
        canonical_id_found = True
    elif id_utils.is_orcid(q):
        normalized_id = id_utils.normalize_orcid(q)
        orcid_id = f"https://orcid.org/{normalized_id}"
        s = s.filter("term", ids__orcid=orcid_id)
        canonical_id_found = True
    elif id_utils.is_wikidata(q):
        normalized_id = id_utils.normalize_wikidata(q)
        wikidata_id = f"https://www.wikidata.org/wiki/{normalized_id}"
        s = s.filter("term", ids__wikidata=wikidata_id)
        canonical_id_found = True
    elif id_utils.is_ror(q):
        normalized_id = id_utils.normalize_ror(q)
        ror_id = f"https://ror.org/{normalized_id}"
        s = s.filter("term", ror=ror_id)
        canonical_id_found = True
    elif id_utils.is_issn(q):
        normalized_id = id_utils.normalize_issn(q)
        s = s.filter("term", ids__issn__lower=normalized_id.upper())
        canonical_id_found = True
    elif id_utils.is_doi(q):
        normalized_id = id_utils.normalize_doi(q)
        doi = f"https://doi.org/{normalized_id}"
        s = s.filter("term", ids__doi=doi)
        canonical_id_found = True
    return s, canonical_id_found


def filter_openalex_id(q, s):
    normalized_id = id_utils.normalize_openalex_id(q)
    openalex_id = f"https://openalex.org/{normalized_id}"
    s = s.filter("term", ids__openalex=openalex_id)
    return s


def is_valid_year(year_str):
    if len(year_str) != 4:
        return False
    try:
        int(year_str)
        return True
    except ValueError:
        return False


def is_valid_year_range(year_range_str):
    if len(year_range_str.split("-")) != 2:
        return False
    start_year, end_year = year_range_str.split("-")
    return is_valid_year(start_year) and is_valid_year(end_year)


def is_year_query(query_str):
    """Check if a string matches a year or a range of years."""
    if len(query_str) >= 1 and query_str[0] in ["<", "-", ">"]:
        return is_valid_year(query_str[1:])
    elif len(query_str) >= 1 and query_str[-1] == "-":
        return is_valid_year(query_str[:-1])
    elif "-" in query_str:
        return is_valid_year_range(query_str)
    else:
        return is_valid_year(query_str)
