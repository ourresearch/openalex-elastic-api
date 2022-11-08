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
        assert json_data1["results"][0]["id"] == "https://openalex.org/C41008148"
        cursor = json_data1["meta"]["next_cursor"]

        res2 = client.get(f"/concepts?cursor={cursor}")
        json_data2 = res2.get_json()
        assert json_data2["results"][0]["id"] == "https://openalex.org/C66938386"

    def test_invalid_cursor_different_sort_size(self, client):
        res1 = client.get("/concepts?cursor=IlswLjAsIDFdIg==&sort=display_name")
        json_data = res1.get_json()
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "Cursor value is invalid."

    def test_cursor_with_page(self, client):
        res1 = client.get("/concepts?cursor=IlswLjAsIDFdIg==&page=2")
        json_data = res1.get_json()
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "Cannot use page parameter with cursor."
