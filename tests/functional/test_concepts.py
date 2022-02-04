import pytest


class TestConceptsSearch:
    def test_concepts_search(self, client):
        res = client.get("/concepts?filter=display_name.search:science")
        json_data = res.get_json()
        assert "science" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "science" in result["display_name"].lower()

    @pytest.mark.skip
    def test_concepts_search_exact(self, client):
        res = client.get("/concepts?filter=display_name:science")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"].lower() == "science"


class TestConceptsWorksCountFilter:
    def test_concepts_works_count_equal(self, client):
        res = client.get("/concepts?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_concepts_works_count_greater_than(self, client):
        res = client.get("/concepts?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9982
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_concepts_works_count_less_than(self, client):
        res = client.get("/concepts?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 14
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_concepts_works_count_error(self, client):
        res = client.get("/concepts?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestConceptsCitedByCountFilter:
    def test_concepts_cited_by_count_equal(self, client):
        res = client.get("/concepts?filter=cited_by_count:0")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 0

    def test_concepts_cited_by_count_greater_than(self, client):
        res = client.get("/concepts?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9995
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_concepts_cited_by_count_less_than(self, client):
        res = client.get("/concepts?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_concepts_cited_by_count_error(self, client):
        res = client.get("/concepts?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestConceptsLevelFilter:
    def test_concepts_level_equal(self, client):
        res = client.get("/concepts?filter=level:2")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3042
        for result in json_data["results"][:25]:
            assert result["level"] == 2

    def test_concepts_level_or_query(self, client):
        res = client.get("/concepts?filter=level:1,level:2")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3142
        for result in json_data["results"][:25]:
            assert result["level"] == 1 or result["level"] == 2

    def test_concepts_level_greater_than(self, client):
        res = client.get("/concepts?filter=level:>2")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6848
        for result in json_data["results"][:25]:
            assert result["level"] > 2

    def test_concepts_level_less_than(self, client):
        res = client.get("/concepts?filter=level:<4")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6717
        for result in json_data["results"][:25]:
            assert result["level"] < 4

    def test_concepts_level_error(self, client):
        res = client.get("/concepts?filter=level:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param level must be a number."


class TestConceptsAncestorsIDFilter:
    def test_concepts_ancestors_id_short(self, client):
        res = client.get("/concepts?filter=ancestors.id:C142362112")
        json_data = res.get_json()
        ancestor_id_found = False
        for ancestor in json_data["results"][0]["ancestors"]:
            if ancestor["id"] == "https://openalex.org/C142362112":
                ancestor_id_found = True
        assert ancestor_id_found == True

    def test_concepts_ancestors_id_long(self, client):
        res = client.get(
            "/concepts?filter=ancestors.id:https://openalex.org/c142362112"
        )
        json_data = res.get_json()
        ancestor_id_found = False
        for ancestor in json_data["results"][0]["ancestors"]:
            if ancestor["id"] == "https://openalex.org/C142362112":
                ancestor_id_found = True
        assert ancestor_id_found == True
