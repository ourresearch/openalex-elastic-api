import re


def is_openalex_id(openalex_id):
    if not openalex_id:
        return False
    openalex_id = openalex_id.lower()
    if re.findall(r"http[s]://openalex.org/([waicv]\d{2,})", openalex_id):
        return True
    if re.findall(r"^([waicv]\d{2,})", openalex_id):
        return True
    if re.findall(r"(openalex:[waicv]\d{2,})", openalex_id):
        return True
    return False


def normalize_openalex_id(openalex_id):
    if not openalex_id:
        return None
    openalex_id = openalex_id.strip().upper()
    p = re.compile("([WAICV]\d{2,})")
    matches = re.findall(p, openalex_id)
    if len(matches) == 0:
        return None
    clean_openalex_id = matches[0]
    clean_openalex_id = clean_openalex_id.replace("\0", "")
    return clean_openalex_id


def is_work_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    return clean_id.startswith("W")


def is_author_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    return clean_id.startswith("A")


def is_venue_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    return clean_id.startswith("V")


def is_institution_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    return clean_id.startswith("I")


def is_concept_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    return clean_id.startswith("C")


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


def normalize_issn(issn):
    if not issn:
        return None
    issn = issn.strip().lower()
    p = re.compile("[\dx]{4}-[\dx]{4}")
    matches = re.findall(p, issn)
    if len(matches) == 0:
        return None
    issn = matches[0]
    issn = issn.replace("\0", "")
    return issn


def normalize_wikidata(wikidata):
    if not wikidata:
        return None
    wikidata = wikidata.strip().upper()
    p = re.compile("Q\d*")
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
    p = re.compile("(\d+)")
    matches = re.findall(p, pmid)
    if len(matches) == 0:
        return None
    pmid = matches[0]
    pmid = pmid.replace("\0", "")
    return pmid
