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


class TestEntitiesAutoComplete:
    def test_authors_autocomplete(self, client):
        res = client.get("/autocomplete/authors?q=jas")
        json_data = res.get_json()
        assert "jas" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jas" in result["display_name"].lower()

    def test_concepts_autocomplete(self, client):
        res = client.get("/autocomplete/concepts?q=sci")
        json_data = res.get_json()
        assert "sci" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "sci" in result["display_name"].lower()

    def test_institutions_autocomplete(self, client):
        res = client.get("/autocomplete/institutions?q=uni")
        json_data = res.get_json()
        assert "uni" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "uni" in result["display_name"].lower()

    def test_venues_autocomplete(self, client):
        res = client.get("/autocomplete/venues?q=nat")
        json_data = res.get_json()
        assert "nat" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "nat" in result["display_name"].lower()

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


class TestCustomAutocomplete:
    def test_institutions_type_autocomplete(self, client):
        res = client.get("/autocomplete/institutions/type?q=co")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"] == "company"
        assert json_data["results"][0]["cited_by_count"] == 39283175


class TestFiltersInAutocomplete:
    def test_authors_filters_autocomplete(self, client):
        res = client.get(
            "/autocomplete/authors?filter=last_known_institution.country_code:be&q=pet"
        )
        json_data = res.get_json()
        assert "peter vandenabeele" in json_data["results"][0]["display_name"].lower()

    def test_concepts_filters_autocomplete(self, client):
        res = client.get("/autocomplete/concepts?filter=level:3&q=ele")
        json_data = res.get_json()
        assert "electrochemistry" in json_data["results"][0]["display_name"].lower()

    def test_institutions_filters_autocomplete(self, client):
        res = client.get("/autocomplete/institutions?filter=country_code:ge&q=sho")
        json_data = res.get_json()
        assert "shota rustaveli" in json_data["results"][0]["display_name"].lower()

    def test_venues_filters_autocomplete(self, client):
        res = client.get("/autocomplete/venues?filter=publisher:wiley&q=chem")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert "wiley" in result["hint"].lower()

    def test_works_filters_autocomplete(self, client):
        res = client.get(
            "/autocomplete/works?filter=is_oa:true,publication_year:2019&q=tra"
        )
        json_data = res.get_json()
        assert (
            "impacts of automated vehicles"
            in json_data["results"][0]["display_name"].lower()
        )

    def test_works_filters_autocomplete_error(self, client):
        res = client.get(
            "/autocomplete/works?filter=is_oaa:true,publication_year:2019&q=tra"
        )
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert "is_oaa is not a valid field" in json_data["message"]

    def test_full_autocomplete_filter_error(self, client):
        res = client.get("/autocomplete?filter=is_oaa:true,publication_year:2019&q=tra")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            "filter is not a valid parameter for the full autocomplete endpoint"
            in json_data["message"]
        )
