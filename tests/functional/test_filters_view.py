class TestFiltersView:
    def test_basic_filters(self, client):
        res = client.get("/works/filters/is_oa:true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "is_oa"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["display_name"] == "true"
        assert filter_1["values"][0]["count"] == 7709

    def test_filter_with_search(self, client):
        res = client.get("/works/filters/display_name.search:science,is_oa:true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "display_name.search"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["display_name"] == "science"
        assert filter_1["values"][0]["count"] == 36
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "is_oa"
        assert filter_2["is_negated"] == False
        assert filter_2["values"][0]["display_name"] == "true"
        assert filter_2["values"][0]["count"] == 25

    def test_filter_with_search_negation(self, client):
        res = client.get("/works/filters/display_name.search:science,is_oa:!true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "display_name.search"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["display_name"] == "science"
        assert filter_1["values"][0]["count"] == 36
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "is_oa"
        assert filter_2["is_negated"] == True
        assert filter_2["values"][0]["display_name"] == "true"
        assert filter_2["values"][0]["count"] == 25

    def test_filter_convert_id(self, client):
        res = client.get("/works/filters/host_venue.id:V90590500")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "host_venue.id"
        assert filter_1["values"][0]["value"] == "V90590500"
        assert filter_1["values"][0]["display_name"] == "Brazilian Journal of Biology"

    def test_filter_convert_country(self, client):
        res = client.get("/works/filters/institutions.country_code:ca")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "institutions.country_code"
        assert filter_1["values"][0]["value"] == "ca"
        assert filter_1["values"][0]["display_name"] == "Canada"

    def test_filter_multiple(self, client):
        res = client.get(
            "/works/filters/display_name.search:the,concepts.id:!C556758197%7CC73283319"
        )
        json_data = res.get_json()
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "concepts.id"
        assert filter_2["is_negated"] == True
        assert filter_2["values"][0]["value"] == "C556758197"
        assert filter_2["values"][0]["count"] == 9
        assert filter_2["values"][1]["value"] == "C73283319"
        assert filter_2["values"][1]["count"] == 4
