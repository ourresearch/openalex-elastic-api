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


class TestVenuesIDGet:
    id_result = "https://openalex.org/V41354064"
    name_result = "ChemInform"

    def test_venues_openalex_get(self, client):
        res = client.get("/venues/V41354064")
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_venues_issn_get_key(self, client):
        res = client.get("/venues/issn:1431-5890", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == self.id_result
        assert json_data["display_name"] == self.name_result

    def test_venues_id_bad_issn(self, client):
        res = client.get("/venues/issn:778-333", follow_redirects=True)
        assert res.status_code == 404

    def test_venues_id_get_bad_data(self, client):
        res = client.get("/venues/289744280", follow_redirects=True)
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

    def test_venues_openalex_get(self, client):
        res = client.get("/V41354064", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/V41354064"
        assert json_data["display_name"] == "ChemInform"

    def test_concepts_openalex_get(self, client):
        res = client.get("/C86803240", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/C86803240"
        assert json_data["display_name"] == "Biology"
