class TestFiltersView:
    def test_basic_filters(self, client):
        res = client.get("/works/filters/is_oa:true")
        json_data = res.get_json()
        filter_1 = json_data["filters"][0]
        assert filter_1["key"] == "is_oa"
        assert filter_1["is_negated"] == False
        assert filter_1["values"][0]["display_name"] == "true"
        assert filter_1["values"][0]["count"] == 7709
