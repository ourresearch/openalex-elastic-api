import re

from elasticsearch_dsl import Q, Search

from core.exceptions import APIQueryParamsError
from core.utils import check_select_field, normalize_openalex_id, select_fields


def is_openalex_id(openalex_id):
    if not openalex_id:
        return False
    openalex_id = openalex_id.lower()
    if re.findall(r"http[s]://openalex.org/([waicfvpstg]\d{2,})", openalex_id):
        return True
    if re.findall(r"^([waicfvpstg]\d{2,})", openalex_id):
        return True
    if re.findall(r"(openalex:[waicfvpstg]\d{2,})", openalex_id):
        return True
    # Also check for uppercase G (awards) since normalize_openalex_id handles it
    if re.findall(r"^([G]\d{2,})", openalex_id.upper()):
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


def is_topic_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("T")


def is_award_openalex_id(id):
    if isinstance(id, int):
        return False
    clean_id = normalize_openalex_id(id)
    if not clean_id:
        return False
    return clean_id.startswith("G")


def is_doi(doi):
    doi = doi.strip().lower()
    if re.search(r"(doi:)?10\.\d+/[^\s]+", doi):
        return True
    return False


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
        r"orcid:\d{4}-\d{4}-\d{4}-\d{3}[\dx]", orcid.lower().strip()
    ) or re.search(r"orcid.org/\d{4}-\d{4}-\d{4}-\d{3}[\dx]", orcid.lower().strip()):
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
    if scopus.startswith("http"):
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
    if re.fullmatch(r"(issn:)?[\dx]{4}-[\dx]{4}", issn):
        return True
    return False


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


def wikidata_forms(qid):
    """Every form an entity index may store Wikidata id `qid` in (oxjob #1884): the indexes mix /entity/
    and /wiki/ URLs, with and without www, and bare Q ids, so a lookup that builds one form misses the rest."""
    return [qid] + [
        f"{scheme}{host}/{path}/{qid}"
        for scheme in ("https://", "http://", "")
        for host in ("www.wikidata.org", "wikidata.org")
        for path in ("wiki", "entity")
    ]


def wikidata_query(field, value):
    """A terms query on `field` matching the Wikidata id in `value` (wikidata:Q42 or a Wikidata URL) in every stored
    form, or None when `value` holds no Q id."""
    qid = normalize_wikidata(value)
    return Q("terms", **{field: wikidata_forms(qid)}) if qid else None


def normalize_wikidata(wikidata):
    if not wikidata:
        return None
    wikidata = wikidata.strip().upper()
    p = re.compile(r"Q\d+")
    matches = re.findall(p, wikidata)
    if len(matches) == 0:
        return None
    wikidata = matches[0]
    wikidata = wikidata.replace("\0", "")
    return wikidata


WORK_ID_SCHEMES = ("doi", "pmid", "pmcid", "mag", "arxiv", "openalex")


def lower_scheme(value, schemes=WORK_ID_SCHEMES):
    """'DOI:10.1/x' -> 'doi:10.1/x', 'arXiv:2305.18290' -> 'arxiv:2305.18290'. Id schemes are case-insensitive;
    the value after the colon keeps its case (oxjob #2157: DOI:, PMID:, PMCID:, MAG: answered 404)."""
    m = re.match(r"([A-Za-z]+):", value)
    if m and m.group(1).lower() in schemes:
        return m.group(1).lower() + value[len(m.group(1)):]
    return value


def is_bare_doi(value):
    """A DOI with no prefix, '10.1038/nature12373'. Must START with 10.<registrant>/ so no other id form matches."""
    return re.match(r"10\.\d{4,9}/\S", value.strip()) is not None


# new-style 2305.18290 (2007-); old-style hep-th/9901001 or math.AG/0309136, whose subject class (.AG) is not part
# of the id (arxiv.org/help/arxiv_identifier). Version (v2) and .pdf are dropped: arXiv's DOI names the paper.
_ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?/?"
_ARXIV_FORM = re.compile(r"(?:arxiv:\s*|(?:https?:/{1,2})?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/)(.*)$", re.I)


def arxiv_form(value):
    """The text after 'arxiv:' or an arxiv.org abs/pdf URL, or None when the value is no arXiv form at all.
    The path router may collapse the // after the scheme (oxjob #850), hence /{1,2}."""
    m = _ARXIV_FORM.match(value.strip())
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", value.strip()):  # a bare new-style id: no other id has this shape
        return value.strip()
    return None


def normalize_arxiv(value):
    """'arxiv:2305.18290v2', 'https://arxiv.org/pdf/2305.18290v2.pdf' -> '2305.18290'; 'arXiv:math.AG/0309136v1'
    -> 'math/0309136'. None if it isn't a well-formed arXiv id."""
    m = re.fullmatch(_ARXIV_ID, value.strip(), re.I)
    if not m:
        return None
    arxiv_id = m.group(1).lower()
    if "/" in arxiv_id:
        archive, number = arxiv_id.split("/")
        arxiv_id = f"{archive.split('.')[0]}/{number}"
    return arxiv_id


def arxiv_doi(arxiv_id):
    """arXiv's DataCite DOI for a paper, in the lower-case URL form ids.doi and the Lakebase id map hold."""
    return f"https://doi.org/10.48550/arxiv.{arxiv_id}"


def arxiv_copy_urls(arxiv_id):
    """The pages an arXiv copy is stored under in locations_full.landing_page_url (forms seen on live works,
    11 Nov 2026): the DOI record, abs and pdf pages, http or https, with or without a version."""
    urls = [arxiv_doi(arxiv_id), f"https://doi.org/10.48550/arXiv.{arxiv_id}"]
    for v in [""] + [f"v{n}" for n in range(1, 10)]:
        for base in ("http://arxiv.org/abs/", "https://arxiv.org/abs/", "http://arxiv.org/pdf/",
                     "https://arxiv.org/pdf/"):
            urls.append(f"{base}{arxiv_id}{v}")
        urls.append(f"https://arxiv.org/pdf/{arxiv_id}{v}.pdf")
    return urls


def is_pubmed_url(value):
    """https://pubmed.ncbi.nlm.nih.gov/<n> (the served ids.pmid form) or the legacy www.ncbi.nlm.nih.gov/pubmed/<n>.
    Substring match because the path router may collapse the // after the scheme (oxjob #850)."""
    value = value.lower()
    return "pubmed.ncbi.nlm.nih.gov/" in value or "ncbi.nlm.nih.gov/pubmed/" in value


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


def normalize_pmcid(pmcid):
    if not pmcid:
        return None
    pmcid = pmcid.strip().lower()
    p = re.compile(r"(\d+)")
    matches = re.findall(p, pmcid)
    if len(matches) == 0:
        return None
    pmcid = matches[0]
    pmcid = pmcid.replace("\0", "")
    return pmcid


def normalize_scopus_id(scopus_id):
    if not scopus_id:
        return None
    try:
        short_scopus_id = int(scopus_id)
        return f"http://www.scopus.com/inward/authorDetails.url?authorID={short_scopus_id}&partnerID=MN8TOARS"
    except ValueError:
        return None


def process_id_only_fields(request, schema):
    schema_fields = [f for f in schema._declared_fields]
    only_fields = select_fields(request)  # None for an empty select= (oxjob #1913)
    if only_fields:
        for field in only_fields:
            check_select_field(field, schema_fields)
    return only_fields
