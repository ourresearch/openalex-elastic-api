class TestBasicPagination:
    def test_pagination_page_1(self, client):
        res = client.get("/works?page=1")
        json_data = res.get_json()
        assert json_data["meta"]["page"] == 1
        assert len(json_data["results"]) == 25

    def test_pagination_page_2(self, client):
        res = client.get("/works?page=2")
        json_data = res.get_json()
        assert json_data["meta"]["page"] == 2
        assert len(json_data["results"]) == 25

    def test_pagination_page_less_than_1(self, client):
        res = client.get("/works?page=0")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "Page parameter must be greater than 0."

    def test_pagination_per_page_valid(self, client):
        res = client.get("/works?per-page=50")
        json_data = res.get_json()
        assert json_data["meta"]["per_page"] == 50

    def test_pagination_per_page_valid_underscore(self, client):
        res = client.get("/works?per_page=50")
        json_data = res.get_json()
        assert json_data["meta"]["per_page"] == 50

    def test_pagination_per_page_error(self, client):
        res = client.get("/works?per-page=ff")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Param per-page must be a number."

    def test_pagination_max_per_page_exceeded(self, client):
        res = client.get("/works?per-page=201")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "per-page parameter must be between 1 and 200"

    def test_pagination_max_results(self, client):
        res = client.get("/works?page=999&per-page=50")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Pagination error."
        assert (
            json_data["message"]
            == "Maximum results size of 10,000 records is exceeded. Cursor pagination is required for records beyond 10,000 and is coming soon."
        )


class TestCursorPagination:
    def test_cursor_pagination_no_cursor(self, client):
        res = client.get("/works")
        json_data = res.get_json()
        assert "next_cursor" not in json_data["meta"]

    def test_cursor_pagination_display_cursor(self, client):
        res = client.get("/works?cursor=*")
        json_data = res.get_json()
        assert "next_cursor" in json_data["meta"]

    def test_cursor_pagination_null_cursor(self, client):
        res = client.get("/works?cursor=null")
        json_data = res.get_json()
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "Cursor is null. Likely reached end of results."

    def test_cursor_pagination(self, client):
        res1 = client.get("/works?cursor=*")
        json_data1 = res1.get_json()
        display_name = json_data1["results"][0]["display_name"]
        next_cursor = json_data1["meta"]["next_cursor"]
        for i in range(1, 10):
            res2 = client.get(f"/works?cursor={next_cursor}")
            json_data2 = res2.get_json()
            assert res2.status_code == 200
            assert json_data2["results"][0]["display_name"] != display_name
            # set for next loop
            next_cursor = json_data2["meta"]["next_cursor"]
            display_name = json_data2["results"][0]["display_name"]
