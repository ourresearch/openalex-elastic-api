class TestPagination:
    def test_pagination_page_valid(self, client):
        res = client.get("/works?page=2")
        json_data = res.get_json()
        assert json_data["meta"]["page"] == 2

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

    def test_pagination_max_per_page_exceeded(self, client):
        res = client.get("/works?per-page=100")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Pagination error."
        assert json_data["message"] == "per-page parameter must be between 1 and 50"

    def test_pagination_max_results(self, client):
        res = client.get("/works?page=999&per-page=50")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Pagination error."
        assert (
            json_data["message"]
            == "Maximum results size of 10,000 records is exceeded. Cursor pagination is required for records beyond 10,000 and is coming soon."
        )
