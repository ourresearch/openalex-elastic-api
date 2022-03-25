class TestSort:
    def test_sort_empty_search_query(self, client):
        res = client.get("/works?filter=display_name.search:&sort=relevance_score:desc")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Must include a search query (such as filter=display_name.search:example) in order to sort by relevance_score."
        )

    def test_sort_search_query(self, client):
        res1 = client.get(
            "/works?filter=display_name.search:science&sort=relevance_score:desc"
        )
        json_data1 = res1.get_json()
        res2 = client.get("/works?filter=display_name.search:science")
        json_data2 = res2.get_json()
        assert (
            json_data1["results"][0]["display_name"]
            == json_data2["results"][0]["display_name"]
        )
