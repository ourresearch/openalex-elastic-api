import re

from elasticsearch_dsl import Q, Search

from core.exceptions import APIQueryParamsError
from core.utils import normalize_openalex_id


def is_openalex_id(openalex_id):
    if not openalex_id:
        return False
    openalex_id = openalex_id.lower()
    if re.findall(r"http[s]://openalex.org/([waicfvps]\d{2,})", openalex_id):
        return True
    if re.findall(r"^([waicfvps]\d{2,})", openalex_id):
        return True
    if re.findall(r"(openalex:[waicfvps]\d{2,})", openalex_id):
        return True
    return False


def is_work_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("W")


def is_author_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("A")


def is_venue_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("V")


def is_institution_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("I")


def is_concept_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("C")


def is_funder_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("F")


def is_publisher_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("P")


def is_source_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("S")


def is_doi(doi):
    if re.search(r"doi:10\.\d+/[^\s]+", doi.strip()) or re.search(
        r"doi.org/10\.\d+/[^\s]+", doi.strip()
    ):
        return True


def normalize_doi(doi, return_none_if_error=False):
    if not doi:
        if return_none_if_error:
            return None
        else:
            raise NoDoiException("There's no DOI at all.")

    doi = doi.strip().lower()

    # test cases for this regex are at https://regex101.com/r/zS4hA0/4
    p = re.compile(r"(10\.\d+/[^\s]+)")
    matches = re.findall(p, doi)

    if len(matches) == 0:
        if return_none_if_error:
            return None
        else:
            raise NoDoiException("There's no valid DOI.")

    doi = matches[0]

    # clean_doi has error handling for non-utf-8
    # but it's preceded by a call to remove_nonprinting_characters
    # which calls to_unicode_or_bust with no error handling
    # clean/normalize_doi takes a unicode object or utf-8 basestring or dies
    doi = to_unicode_or_bust(doi)

    return doi.replace("\0", "")


def to_unicode_or_bust(obj, encoding="utf-8"):
    if isinstance(obj, str):
        if not isinstance(obj, str):
            obj = str(obj, encoding)
    return obj


class NoDoiException(Exception):
    pass


def is_orcid(orcid):
    if re.search(
        r"orcid:\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid.lower().strip()
    ) or re.search(r"orcid.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid.lower().strip()):
        return True


def normalize_orcid(orcid):
    if not orcid:
        return None
    orcid = orcid.strip().upper()
    p = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")
    matches = re.findall(p, orcid)
    if len(matches) == 0:
        return None
    orcid = matches[0]
    orcid = orcid.replace("\0", "")
    return orcid


def normalize_scopus(scopus):
    # returns just the scopus ID
    if not scopus:
        return None
    scopus = scopus.strip().lower()
    if scopus.startswith('http'):
        p = re.compile(r"authorID=(\d+)")
        matches = re.findall(p, scopus)
        if len(matches) == 0:
            return None
        scopus = matches[0]
    scopus = scopus.replace("\0", "")
    return scopus


def is_ror(ror):
    if re.search(r"(ror:[a-z\d]*$)", ror.lower().strip()) or re.search(
        r"(ror.org/[a-z\d]*$)", ror.lower().strip()
    ):
        return True


def normalize_ror(ror):
    if not ror:
        return None
    ror = ror.strip().lower()
    p = re.compile(r"([a-z\d]*$)")
    matches = re.findall(p, ror)
    if len(matches) == 0:
        return None
    ror = matches[0]
    ror = ror.replace("\0", "")
    return ror


def is_issn(issn):
    issn = issn.strip().lower()
    if re.search(r"issn:[\dx]{4}-[\dx]{4}", issn) or re.search(
        r"portal.issn.org/resource/issn/[\dx]{4}-[\dx]{4}", issn
    ):
        return True


def normalize_issn(issn):
    if not issn:
        return None
    issn = issn.strip().lower()
    p = re.compile(r"[\dx]{4}-[\dx]{4}")
    matches = re.findall(p, issn)
    if len(matches) == 0:
        return None
    issn = matches[0]
    issn = issn.replace("\0", "")
    return issn


def is_wikidata(wikidata):
    if re.search(r"wikidata:q\d*", wikidata.lower().strip()) or re.search(
        r"wikidata.org/wiki/q\d*", wikidata.lower().strip()
    ):
        return True


def normalize_wikidata(wikidata):
    if not wikidata:
        return None
    wikidata = wikidata.strip().upper()
    p = re.compile(r"Q\d*")
    matches = re.findall(p, wikidata)
    if len(matches) == 0:
        return None
    wikidata = matches[0]
    wikidata = wikidata.replace("\0", "")
    return wikidata


def normalize_pmid(pmid):
    if not pmid:
        return None
    pmid = pmid.strip().lower()
    p = re.compile(r"(\d+)")
    matches = re.findall(p, pmid)
    if len(matches) == 0:
        return None
    pmid = matches[0]
    pmid = pmid.replace("\0", "")
    return pmid


def get_merged_id(index_name, full_openalex_id):
    merged_id = None
    s = Search(index=index_name)
    s = s.filter(Q("term", id__keyword=full_openalex_id))
    response = s.execute()
    for item in response:
        if "merge_into_id" in item:
            merged_id = item.merge_into_id
            merged_id = normalize_openalex_id(merged_id)
    return merged_id


def process_id_only_fields(request, schema):
    schema_fields = [f for f in schema._declared_fields]
    only_fields = request.args.get("select")
    if only_fields:
        only_fields = only_fields.split(",")
        only_fields = [f.strip() for f in only_fields]
        for field in only_fields:
            if field not in schema_fields:
                raise APIQueryParamsError(
                    f"{field} is not a valid select field. Valid fields for select are: {', '.join(schema_fields)}."
                )
    return only_fields
