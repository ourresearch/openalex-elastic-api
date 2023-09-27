from collections import OrderedDict

from elasticsearch_dsl import Q, Search

from autocomplete.utils import AUTOCOMPLETE_SOURCE
from autocomplete.validate import validate_entity_autocomplete_params
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import full_search_query
from core.utils import clean_preference, map_filter_params
from ids import utils as id_utils


def single_entity_autocomplete(fields_dict, index_name, request):
    # params
    validate_entity_autocomplete_params(request)
    filter_params = map_filter_params(request.args.get("filter"))
    q = request.args.get("q")
    search = request.args.get("search")

    s = Search(index=index_name)
    canonical_id_found = False

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

        if q:
            # autocomplete
            if index_name.startswith("author"):
                s = s.query(
                    Q("match_phrase_prefix", display_name__autocomplete=q)
                    | Q(
                        "match_phrase_prefix", display_name_alternatives__autocomplete=q
                    )
                )
            elif index_name.startswith("institution"):
                s = s.query(
                    Q("match_phrase_prefix", display_name__autocomplete=q)
                    | Q("match_phrase_prefix", display_name_acronyms__autocomplete=q)
                    | Q(
                        "match_phrase_prefix", display_name_alternatives__autocomplete=q
                    )
                )
            elif index_name.startswith("source"):
                s = s.query(
                    Q("match_phrase_prefix", display_name__autocomplete=q)
                    | Q("match_phrase_prefix", alternate_titles__autocomplete=q)
                    | Q("match_phrase_prefix", abbreviated_title__autocomplete=q)
                )
            elif index_name.startswith("works") and is_year(q):
                s = s.filter("term", publication_year=q)
            else:
                s = s.query("match_phrase_prefix", display_name__autocomplete=q)
        s = s.sort("-cited_by_count")
        s = s.source(AUTOCOMPLETE_SOURCE)
        preference = clean_preference(q)
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


def search_canonical_id_single(index_name, s, q):
    canonical_id_found = False
    if (
        (index_name.startswith("author") and id_utils.is_author_openalex_id(q))
        or (index_name.startswith("concept") and id_utils.is_concept_openalex_id(q))
        or (
            index_name.startswith("institution")
            and id_utils.is_institution_openalex_id(q)
        )
        or (index_name.startswith("venue") and id_utils.is_venue_openalex_id(q))
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
    elif (index_name.startswith("venue") and id_utils.is_issn(q)) or (
        index_name.startswith("source") and id_utils.is_issn(q)
    ):
        normalized_id = id_utils.normalize_issn(q)
        s = s.filter("term", issn=normalized_id)
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
        s = s.filter("term", issn=normalized_id.upper())
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


def is_year(q):
    try:
        if int(q) and len(q.strip()) == 4:
            return True
    except ValueError:
        return False
