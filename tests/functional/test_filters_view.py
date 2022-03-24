import pytest


class TestFiltersView:
    def test_basic_filters(self, client):
        res = client.get("/works/filters/is_oa:true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "is_oa"
        assert filter_1["type"] == "BooleanField"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["value"] == "true"
        assert filter_1["values"][0]["display_name"] == "true"
        assert filter_1["values"][0]["count"] == 7709

    def test_filter_with_search(self, client):
        res = client.get("/works/filters/display_name.search:science,is_oa:true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "display_name.search"
        assert filter_1["type"] == "SearchField"
        assert filter_1["values"][0]["value"] == "science"
        assert filter_1["values"][0]["display_name"] == "science"
        assert filter_1["values"][0]["count"] == 25
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "is_oa"
        assert filter_2["type"] == "BooleanField"
        assert filter_2["values"][0]["display_name"] == "true"
        assert filter_2["values"][0]["count"] == 25

    def test_filter_with_search_negation(self, client):
        res = client.get("/works/filters/display_name.search:science,oa_status:!gold")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "display_name.search"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["display_name"] == "science"
        assert filter_1["values"][0]["count"] == 1
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "oa_status"
        assert filter_2["is_negated"] == True
        assert filter_2["values"][0]["display_name"] == "gold"
        assert filter_2["values"][0]["count"] == 1

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
            "/works/filters/display_name.search:the,concepts.id:C556758197%7CC73283319"
        )
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["values"][0]["count"] == 12
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "concepts.id"
        assert filter_2["values"][0]["value"] == "C556758197"
        assert filter_2["values"][0]["count"] == 9
        assert filter_2["values"][1]["value"] == "C73283319"
        assert filter_2["values"][1]["count"] == 4

    def test_filter_multiple_negated(self, client):
        res = client.get(
            "/works/filters/display_name.search:the,concepts.id:!C556758197%7CC73283319"
        )
        json_data = res.get_json()
        filter_2 = json_data["filters"][1]
        assert filter_2["key"] == "concepts.id"
        assert filter_2["is_negated"] == True
        assert filter_2["values"][0]["value"] == "C556758197"
        assert filter_2["values"][0]["count"] == 0
        assert filter_2["values"][1]["value"] == "C73283319"
        assert filter_2["values"][1]["count"] == 0

    @pytest.mark.skip
    def test_filter_url_single(self, client):
        res = client.get("/works/filters/concepts.id:C73283319")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert (
            filter_1["values"][0]["url"]
            == "http://localhost/works?filter=concepts.id:C73283319"
        )

    @pytest.mark.skip
    def test_filter_url_with_search(self, client):
        res = client.get(
            "/works/filters/display_name.search:the,concepts.id:!C556758197"
        )
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert (
            filter_1["values"][0]["url"]
            == "http://localhost/works?filter=display_name.search:the"
        )
        filter_2 = json_data["filters"][1]
        assert (
            filter_2["values"][0]["url"]
            == "http://localhost/works?filter=display_name.search:the,concepts.id:C556758197"
        )
