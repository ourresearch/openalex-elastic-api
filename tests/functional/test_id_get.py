class TestWorksIDGet:
    id_result = "https://openalex.org/W2894744280"
    name_result = "Fusing Location Data for Depression Prediction"

    def test_works_openalex_get(self, client):
        res = client.get("/works/W2894744280")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_openalex_get_case_insensitive(self, client):
        res = client.get("/works/w2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_openalex_get_url(self, client):
        res = client.get(
            "/works/https://openalex.org/W2894744280", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_openalex_get_key(self, client):
        res = client.get("/works/openalex:W2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_doi_get(self, client):
        res = client.get(
            "/works/https://doi.org/10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_doi_get_key(self, client):
        res = client.get(
            "/works/doi:10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_doi_get_partial_url(self, client):
        res = client.get(
            "/works/doi.org/10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_mag_get(self, client):
        res = client.get("/works/mag:2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_works_pmid_get_short(self, client):
        res = client.get("/works/pmid:30295140", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894716986"
        assert json_data["ids"]["pmid"] == "https://pubmed.ncbi.nlm.nih.gov/30295140"

    def test_works_pmid_get_long(self, client):
        res = client.get(
            "/works/pmid:https://pubmed.ncbi.nlm.nih.gov/30295140",
            follow_redirects=True,
        )
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894716986"
        assert json_data["ids"]["pmid"] == "https://pubmed.ncbi.nlm.nih.gov/30295140"

    def test_works_pmid_get_bad_data(self, client):
        res = client.get("/works/pmid:7777777777", follow_redirects=True)
        assert res.status_code == 404

    def test_works_id_get_bad_data(self, client):
        res = client.get("/works/2894744280", follow_redirects=True)
        assert res.status_code == 404


class TestAuthorsIDGet:
    id_result = "https://openalex.org/A2609699"
    name_result = "Peter Vandenabeele"

    def test_authors_openalex_get(self, client):
        res = client.get("/authors/A2609699")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_openalex_get_case_insensitive(self, client):
        res = client.get("/authors/a2609699", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_openalex_get_url(self, client):
        res = client.get(
            "/authors/https://openalex.org/A2609699", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_openalex_get_key(self, client):
        res = client.get("/authors/openalex:A2609699", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_orcid_get(self, client):
        res = client.get(
            "/authors/https://orcid.org/0000-0001-5285-9835", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_orcid_get_key(self, client):
        res = client.get("/authors/orcid:0000-0001-5285-9835", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_mag_get(self, client):
        res = client.get("/authors/mag:2609699", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_authors_id_get_bad_data(self, client):
        res = client.get("/authors/289744280", follow_redirects=True)
        assert res.status_code == 404

    def test_people_openalex_get(self, client):
        res = client.get("/people/A2609699")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result


class TestInstitutionsIDGet:
    id_result = "https://openalex.org/I19820366"
    name_result = "Chinese Academy of Sciences"

    def test_institutions_openalex_get(self, client):
        res = client.get("/institutions/I19820366")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_institutions_ror_get(self, client):
        res = client.get(
            "/institutions/https://ror.org/034t30j35", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_institutions_ror_get_key(self, client):
        res = client.get("/institutions/ror:034t30j35", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_institutions_id_get_bad_data(self, client):
        res = client.get("/institutions/289744280", follow_redirects=True)
        assert res.status_code == 404


class TestConceptsIDGet:
    id_result = "https://openalex.org/C86803240"
    name_result = "Biology"

    def test_concepts_openalex_get(self, client):
        res = client.get("/concepts/C86803240")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_concepts_wikidata_get(self, client):
        res = client.get("/concepts/wikidata:Q420", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_concepts_wikidata_get_key(self, client):
        res = client.get(
            "/concepts/https://www.wikidata.org/wiki/Q420", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_concepts_id_bad_issn(self, client):
        res = client.get("/concepts/wikidata:8899", follow_redirects=True)
        assert res.status_code == 404

    def test_concepts_bad_data(self, client):
        res = client.get("/concepts/289744280", follow_redirects=True)
        assert res.status_code == 404


class TestConceptsNameGet:
    def test_concepts_name_get(self, client):
        res = client.get("/concepts/name/biology")
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/C86803240"
        assert json_data["display_name"] == "Biology"


class TestPublishersIDGet:
    id_result = "https://openalex.org/P4310320006"
    name_result = "American Chemical Society"

    def test_publishers_openalex_get(self, client):
        res = client.get("/publishers/P4310320006")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_publishers_openalex_get_case_insensitive(self, client):
        res = client.get("/publishers/p4310320006", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_publishers_openalex_get_url(self, client):
        res = client.get(
            "/publishers/https://openalex.org/P4310320006", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result


class TestSourcesIDGet:
    id_result = "https://openalex.org/S3880285"
    name_result = "Science"

    def test_sources_openalex_get(self, client):
        res = client.get("/sources/S3880285")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_sources_openalex_get_case_insensitive(self, client):
        res = client.get("/sources/s3880285", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_sources_openalex_get_url(self, client):
        res = client.get(
            "/sources/https://openalex.org/S3880285", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result


class TestUniversalIDGet:
    def test_works_openalex_get(self, client):
        res = client.get("/W2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_authors_openalex_get(self, client):
        res = client.get("/A2609699", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/A2609699"
        assert json_data["display_name"] == "Peter Vandenabeele"

    def test_institutions_openalex_get(self, client):
        res = client.get("/I19820366", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/I19820366"
        assert json_data["display_name"] == "Chinese Academy of Sciences"

    def test_concepts_openalex_get(self, client):
        res = client.get("/C86803240", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/C86803240"
        assert json_data["display_name"] == "Biology"

    def test_publishers_openalex_get(self, client):
        res = client.get("/P4310320006", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/P4310320006"
        assert json_data["display_name"] == "American Chemical Society"

    def test_sources_openalex_get(self, client):
        res = client.get("/S3880285", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/S3880285"
        assert json_data["display_name"] == "Science"


class TestIDSelect:
    def test_works_select(self, client):
        res = client.get("/works/W2894744280?select=id,display_name")
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_authors_select(self, client):
        res = client.get("/authors/A2609699?select=id,display_name")
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_institutions_select(self, client):
        res = client.get("/institutions/I19820366?select=id,display_name")
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_concepts_select(self, client):
        res = client.get("/C86803240?select=id,display_name", follow_redirects=True)
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_publishers_select(self, client):
        res = client.get("/P4310320006?select=id,display_name", follow_redirects=True)
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_sources_select(self, client):
        res = client.get("/S3880285?select=id,display_name", follow_redirects=True)
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}

    def test_universal_select(self, client):
        res = client.get("/W2894744280?select=id,display_name", follow_redirects=True)
        json_data = res.get_json()
        assert json_data.keys() == {"id", "display_name"}
