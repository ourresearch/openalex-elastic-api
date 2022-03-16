class TestCursorPagination:
    def test_no_cursor_without_param(self, client):
        res = client.get("/works")
        json_data = res.get_json()
        assert json_data["meta"].get("next_cursor") is None

    def test_get_cursor(self, client):
        res = client.get("/works?cursor=*")
        json_data = res.get_json()
        assert len(json_data["meta"]["next_cursor"]) > 1
        assert json_data["meta"]["page"] is None

    def test_working_cursor(self, client):
        res1 = client.get("/concepts?cursor=*")
        json_data1 = res1.get_json()
        assert json_data1["results"][0]["id"] == "https://openalex.org/C86803240"
        cursor = json_data1["meta"]["next_cursor"]

        res2 = client.get(f"/concepts?cursor={cursor}")
        json_data2 = res2.get_json()
        assert json_data2["results"][0]["id"] == "https://openalex.org/C1862650"
