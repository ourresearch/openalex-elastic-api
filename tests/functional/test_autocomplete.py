class TestFullAutoComplete:
    def test_full_autocomplete(self, client):
        res = client.get("/autocomplete?q=sci")
        json_data = res.get_json()
        first_object = json_data["results"][0]
        assert first_object["id"] == "https://openalex.org/C41008148"
        assert first_object["display_name"] == "Computer science"
        assert first_object["cited_by_count"] == 116620134
        assert first_object["entity_type"] == "concept"
        assert first_object["external_id"] == "https://www.wikidata.org/wiki/Q21198"

        for result in json_data["results"][:25]:
            assert "sci" in result["display_name"].lower()


class TestAuthorsAutoComplete:
    def test_authors_autocomplete(self, client):
        res = client.get("/autocomplete/authors?q=jas")
        json_data = res.get_json()
        assert "jas" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jas" in result["display_name"].lower()


class TestWorksAutoComplete:
    def test_works_autocomplete(self, client):
        res = client.get("/autocomplete/works?q=list")
        json_data = res.get_json()
        first_object = json_data["results"][0]
        assert first_object["id"] == "https://openalex.org/W121243"
        assert (
            first_object["display_name"]
            == "Cytoskeletal Mechanics: List of Contributors"
        )
        assert first_object["cited_by_count"] == 71
        assert first_object["entity_type"] == "work"
        assert first_object["external_id"] == "https://doi.org/10.1017/cbo9780511607318"

        for result in json_data["results"][:25]:
            assert "list" in result["display_name"].lower()
