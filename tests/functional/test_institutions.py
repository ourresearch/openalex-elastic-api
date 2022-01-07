import pytest


class TestInstitutionsSearch:
    def test_institutions_search(self, client):
        res = client.get("/institutions?filter=display_name.search:university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    @pytest.mark.skip
    def test_institutions_search_exact(self, client):
        res = client.get("/institutions?filter=display_name:university of")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"].lower() == "university of"


class TestInstitutionsWorksCountFilter:
    def test_institutions_works_count_equal(self, client):
        res = client.get("/institutions?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_institutions_works_count_greater_than(self, client):
        res = client.get("/institutions?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6712
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_institutions_works_count_less_than(self, client):
        res = client.get("/institutions?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3279
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_institutions_works_count_error(self, client):
        res = client.get("/institutions?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Range filter for works_count must be a number."


class TestInstitutionsCitedByCountFilter:
    def test_institutions_cited_by_count_equal(self, client):
        res = client.get("/institutions?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_institutions_cited_by_count_greater_than(self, client):
        res = client.get("/institutions?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9914
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_institutions_cited_by_count_less_than(self, client):
        res = client.get("/institutions?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 82
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_institutions_cited_by_count_error(self, client):
        res = client.get("/institutions?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Range filter for cited_by_count must be a number."
        )


class TestInstitutionsXConceptsIDFilter:
    def test_institutions_x_concepts_id_short(self, client):
        res = client.get("/institutions?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_institutions_x_concepts_id_long(self, client):
        res = client.get(
            "/institutions?filter=x_concepts.id:https://openalex.org/c185592680"
        )
        json_data = res.get_json()
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestInstitutionsCountryCodeFilter:
    def test_institutions_country_code(self, client):
        res = client.get("/institutions?filter=country_code:us")
        json_data = res.get_json()
        assert json_data["results"][0]["country_code"].lower() == "us"
        for result in json_data["results"][:25]:
            assert result["country_code"].lower() == "us"


class TestInstitutionsTypeFilter:
    def test_institutions_type(self, client):
        res = client.get("/institutions?filter=type:education")
        json_data = res.get_json()
        assert json_data["results"][0]["type"].lower() == "education"
        for result in json_data["results"][:25]:
            assert result["type"].lower() == "education"
