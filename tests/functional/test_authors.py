import pytest


class TestAuthorsSearch:
    def test_authors_search(self, client):
        res = client.get("/authors?filter=display_name.search:jones")
        json_data = res.get_json()
        assert "jones" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jones" in result["display_name"].lower()

    @pytest.mark.skip
    def test_authors_search_exact(self, client):
        res = client.get("/authors?filter=display_name:stephens")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"].lower() == "stephens"


class TestAuthorWorksCountFilter:
    def test_authors_works_count_equal(self, client):
        res = client.get("/authors?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_authors_works_count_greater_than(self, client):
        res = client.get("/authors?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 98
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_authors_works_count_less_than(self, client):
        res = client.get("/authors?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9900
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_authors_works_count_range(self, client):
        res = client.get("/authors?filter=works_count:200-202")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["works_count"] == 201

    def test_authors_works_count_error(self, client):
        res = client.get("/authors?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestAuthorsCitedByCountFilter:
    def test_authors_cited_by_count_equal(self, client):
        res = client.get("/authors?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 42
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_authors_cited_by_count_greater_than(self, client):
        res = client.get("/authors?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3040
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_authors_cited_by_count_less_than(self, client):
        res = client.get("/authors?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6918
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_authors_cited_by_count_error(self, client):
        res = client.get("/authors?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestAuthorsLastKnownInstitution:
    def test_authors_last_known_institution_id_short(self, client):
        res = client.get("/authors?filter=last_known_institution.id:i32597200")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert (
                result["last_known_institution"]["id"]
                == "https://openalex.org/I32597200"
            )

    def test_authors_last_known_institution_id_long(self, client):
        res = client.get(
            "/authors?filter=last_known_institution.id:https://openalex.org/I32597200"
        )
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert (
                result["last_known_institution"]["id"]
                == "https://openalex.org/I32597200"
            )

    def test_authors_last_known_institution_ror(self, client):
        res = client.get(
            "/authors?filter=last_known_institution.ror:https://ror.org/00cv9y106"
        )
        json_data = res.get_json()
        assert (
            json_data["results"][0]["last_known_institution"]["ror"]
            == "https://ror.org/00cv9y106"
        )

    def test_authors_last_known_institution_country_code_single(self, client):
        res = client.get("/authors?filter=last_known_institution.country_code:us")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert result["last_known_institution"]["country_code"] == "US"

    def test_authors_last_known_institution_country_code_multiple(self, client):
        res = client.get("/authors?filter=last_known_institution.country_code:[us,ca]")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert (
                result["last_known_institution"]["country_code"] == "US"
                or result["last_known_institution"]["country_code"] == "CA"
            )

    def test_authors_last_known_institution_type(self, client):
        res = client.get("/authors?filter=last_known_institution.type:EducAtion")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert result["last_known_institution"]["type"] == "education"


class TestAuthorsXConceptsID:
    def test_authors_x_concepts_id_short(self, client):
        res = client.get("/authors?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_authors_x_concepts_id_long(self, client):
        res = client.get(
            "/authors?filter=x_concepts.id:https://openalex.org/c185592680"
        )
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True
