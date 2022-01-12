import pytest


class TestVenuesSearch:
    def test_venues_search(self, client):
        res = client.get("/venues?filter=display_name.search:university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    @pytest.mark.skip
    def test_venues_search_exact(self, client):
        res = client.get("/venues?filter=display_name:university of")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"].lower() == "university of"


class TestVenuesWorksCountFilter:
    def test_venues_works_count_equal(self, client):
        res = client.get("/venues?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_venues_works_count_greater_than(self, client):
        res = client.get("/venues?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8429
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_venues_works_count_less_than(self, client):
        res = client.get("/venues?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1566
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_venues_works_count_error(self, client):
        res = client.get("/venues?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Range filter for works_count must be a number."


class TestVenuesCitedByCountFilter:
    def test_venues_cited_by_count_equal(self, client):
        res = client.get("/venues?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_venues_cited_by_count_greater_than(self, client):
        res = client.get("/venues?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9776
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_venues_cited_by_count_less_than(self, client):
        res = client.get("/venues?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 221
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_venues_cited_by_count_range(self, client):
        res = client.get("/venues?filter=cited_by_count:20-22")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 21

    def test_venues_cited_by_count_error(self, client):
        res = client.get("/venues?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Range filter for cited_by_count must be a number."
        )


class TestVenuesXConceptsIDFilter:
    def test_venues_x_concepts_id_short(self, client):
        res = client.get("/venues?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_venues_x_concepts_id_long(self, client):
        res = client.get("/venues?filter=x_concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestVenuesOAFilters:
    def test_venues_is_oa(self, client):
        res = client.get("/venues?filter=is_oa:TRue")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1337
        for result in json_data["results"][:25]:
            assert result["is_oa"] == True

    def test_venues_is_in_doaj(self, client):
        res = client.get("/venues?filter=is_in_doaj:FaLse")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7322
        for result in json_data["results"][:25]:
            assert result["is_in_doaj"] == False


class TestVenuesPublisher:
    def test_venues_publisher_single(self, client):
        res = client.get("/venues?filter=publisher:ElseVier")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1074
        for result in json_data["results"]:
            assert result["publisher"] == "Elsevier"

    def test_venues_publisher_multiple(self, client):
        res = client.get("/venues?filter=publisher:[wiley,elsevier]")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1797
        for result in json_data["results"][:25]:
            assert (
                result["publisher"].lower() == "wiley"
                or result["publisher"].lower() == "elsevier"
            )
