class TestPublishersSearch:
    def test_publishers_search(self, client):
        res = client.get("/publishers?search=springer")
        json_data = res.get_json()
        first_result = json_data["results"][0]
        assert first_result["display_name"] == "Springer Nature"

    def test_publishers_search_alternate_names(self, client):
        res = client.get("/publishers?search=Springer Nature group")
        json_data = res.get_json()
        first_result = json_data["results"][0]
        assert first_result["display_name"] == "Springer Nature"

    def test_publishers_search_display_name(self, client):
        res = client.get("/publishers?filter=display_name.search:Elsevier")
        json_data = res.get_json()
        first_result = json_data["results"][0]
        assert first_result["display_name"] == "Elsevier BV"


class TestPublishersHierarchyLevel:
    def test_publisher_hierarchy_level_exact(self, client):
        res = client.get("/publishers?filter=hierarchy_level:0")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6899
        for result in json_data["results"][:25]:
            assert result["hierarchy_level"] == 0

    def test_publisher_hierarchy_level_greater_than(self, client):
        res = client.get("/publishers?filter=hierarchy_level:>1")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 30
        for result in json_data["results"][:25]:
            assert result["hierarchy_level"] > 0

    def test_publisher_hierarchy_level_less_than(self, client):
        res = client.get("/publishers?filter=hierarchy_level:<1")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6899
        for result in json_data["results"][:25]:
            assert result["hierarchy_level"] < 1


class TestPublishersWorksCount:
    def test_publisher_works_count_equal(self, client):
        res = client.get("/publishers?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_publisher_works_count_greater_than(self, client):
        res = client.get("/publishers?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5014
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_publisher_works_count_less_than(self, client):
        res = client.get("/publishers?filter=works_count:<100")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1406
        for result in json_data["results"][:25]:
            assert result["works_count"] < 100


class TestPublishersCitedByCount:
    def test_publisher_cited_by_count_equal(self, client):
        res = client.get("/publishers?filter=cited_by_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 850

    def test_publisher_cited_by_count_greater_than(self, client):
        res = client.get("/publishers?filter=cited_by_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5417
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 200

    def test_publisher_cited_by_count_less_than(self, client):
        res = client.get("/publishers?filter=cited_by_count:<100")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1236
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 100


class TestPublishersIDs:
    def test_publisher_id_openalex(self, client):
        res = client.get("/publishers?filter=openalex:p4310319965")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/P4310319965"

    def test_publisher_id_ror_short(self, client):
        res = client.get("/publishers?filter=ror:0117Jxy09")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["ids"]["ror"] == "https://ror.org/0117jxy09"

    def test_publisher_id_ror_long(self, client):
        res = client.get("/publishers?filter=ror:https://ror.org/0117jXy09")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["ids"]["ror"] == "https://ror.org/0117jxy09"

    def test_publisher_id_wikidata_short(self, client):
        res = client.get("/publishers?filter=wikidata_id:Q21096327")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["ids"]["wikidata"]
            == "https://www.wikidata.org/entity/Q21096327"
        )

    def test_publisher_id_wikidata_long(self, client):
        res = client.get(
            "/publishers?filter=wikidata_id:https://www.wikidata.org/entity/q21096327"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["ids"]["wikidata"]
            == "https://www.wikidata.org/entity/Q21096327"
        )


class TestPublishersCountryCode:
    def test_publisher_country_code(self, client):
        res = client.get("/publishers?filter=country_code:de")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 201
        for result in json_data["results"][:25]:
            assert "DE" in result["country_codes"]


class TestPublisherContinent:
    def test_publisher_continent(self, client):
        res = client.get("/publishers?filter=continent:north_america")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1311


class TestPublisherGroupBy:
    def test_publisher_group_by_country_code(self, client):
        res = client.get("/publishers?group_by=country_code")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 106
        # check first result
        assert json_data["group_by"][1]["key"] == "us"
        assert (
            json_data["group_by"][1]["key_display_name"] == "United States of America"
        )
        assert json_data["group_by"][1]["count"] == 1025

    def test_publisher_group_by_hierarchy_level(self, client):
        res = client.get("/publishers?group_by=hierarchy_level")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        # check first result
        assert json_data["group_by"][0]["key"] == "0"
        assert json_data["group_by"][0]["key_display_name"] == "0"
        assert json_data["group_by"][0]["count"] == 6899
        # check last result
        assert json_data["group_by"][2]["key"] == "2"
        assert json_data["group_by"][2]["key_display_name"] == "2"
        assert json_data["group_by"][2]["count"] == 30


class TestPublisherParentPublisher:
    def test_parent_publisher_short(self, client):
        res = client.get("/publishers?filter=parent_publisher:P4310320990")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        assert (
            json_data["results"][0]["parent_publisher"]
            == "https://openalex.org/P4310320990"
        )

    def test_parent_publisher_long(self, client):
        res = client.get(
            "/publishers?filter=parent_publisher:https://openalex.org/P4310320990"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        assert (
            json_data["results"][0]["parent_publisher"]
            == "https://openalex.org/P4310320990"
        )
