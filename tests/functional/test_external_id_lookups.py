"""oxjob #1884: external-id singleton lookups return the right record in every documented form.

When several records hold one id, the right one is the record holding it as its primary id (ORCID only), then the one
with the most works. Each case is a real one from the job's before sample (live index, 26 Oct 2026). Needs ES."""
import pytest


def _id(client, path):
    res = client.get(path, follow_redirects=True)
    assert res.status_code == 200, f"{path} -> {res.status_code}"
    return res.get_json()["id"].rsplit("/", 1)[-1]


@pytest.mark.parametrize(
    "path, want",
    [
        # 0000-0002-5787-4927: primary ORCID of A5059386507 (878 works); a 2-work splinter observed it and won before
        ("/authors/orcid:0000-0002-5787-4927", "A5059386507"),
        ("/authors/https://orcid.org/0000-0002-5787-4927", "A5059386507"),
        ("/authors/orcid.org/0000-0002-5787-4927", "A5059386507"),
        ("/people/orcid:0000-0002-5787-4927", "A5059386507"),
        ("/authors/orcid:0000-0002-9804-7725", "A5034289521"),
    ],
)
def test_orcid_lookup_prefers_the_primary_holder(client, path, want):
    assert _id(client, path) == want


@pytest.mark.parametrize(
    "path, want",
    [
        # University of Tehran (9,948 works); its sub-unit F4320335107 (229) carries the same ROR
        ("/funders/ror:05vf56z40", "F4320322667"),
        ("/funders/https://ror.org/05vf56z40", "F4320322667"),
        # NSF by Funder DOI and Crossref funder id
        ("/funders/doi:10.13039/100000001", "F4320306076"),
        ("/funders/https://doi.org/10.13039/100000001", "F4320306076"),
        ("/funders/crossref:100000001", "F4320306076"),
        # stored as a /wiki/ URL, not /entity/: 404 before
        ("/funders/wikidata:Q471316", "F4320319784"),
        ("/funders/https://www.wikidata.org/entity/Q471316", "F4320319784"),
        # a Wikidata id on two funders: the one with more works
        ("/funders/wikidata:Q206921", "F4320307765"),
    ],
)
def test_funder_lookups(client, path, want):
    assert _id(client, path) == want


@pytest.mark.parametrize(
    "path, want",
    [
        # docs: Wikidata is publishers' canonical id; stored as /wiki/ here, /entity/ for Elsevier
        ("/publishers/wikidata:Q30264942", "P4362643903"),
        ("/publishers/https://www.wikidata.org/wiki/Q30264942", "P4362643903"),
        ("/publishers/wikidata:Q746413", "P4310320990"),
        ("/publishers/https://www.wikidata.org/entity/Q746413", "P4310320990"),
        # an imprint shares its group's ROR: the group (more works) wins
        ("/publishers/ror:02rxc7m23", "P4310320988"),
    ],
)
def test_publisher_lookups(client, path, want):
    assert _id(client, path) == want


def test_institution_wikidata_stored_bare(client):
    # institutions-v8 stores 12,329 Wikidata ids as bare Q ids
    assert _id(client, "/institutions/wikidata:Q4743139") == "I4405258391"


@pytest.mark.parametrize(
    "path",
    [
        "/works/https://pubmed.ncbi.nlm.nih.gov/29456894",
        "/works/pmid:https://pubmed.ncbi.nlm.nih.gov/29456894",
        "/works/https://www.ncbi.nlm.nih.gov/pubmed/29456894",
        "/works/pmid:29456894",
        "/v2/works/https://pubmed.ncbi.nlm.nih.gov/29456894",
    ],
)
def test_works_by_pubmed_url(client, path):
    assert _id(client, path) == "W2741809807"


@pytest.mark.parametrize(
    "path",
    ["/funders/crossref:abc", "/funders/doi:not-a-doi", "/publishers/wikidata:Q", "/works/https://pubmed.ncbi.nlm.nih.gov/x"],
)
def test_malformed_ids_404(client, path):
    assert client.get(path, follow_redirects=True).status_code == 404
