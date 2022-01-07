class TestGroupByParam:
    def test_group_by_param_underscore(self, client):
        res = client.get("/works?group_by=publication_year")
        json_data = res.get_json()
        for group in json_data["group_by"][:10]:
            assert len(group["key"]) == 4
            assert type(group["count"]) == int

    def test_group_by_param_hyphen(self, client):
        res = client.get("/works?group-by=publication_year")
        json_data = res.get_json()
        for group in json_data["group_by"][:10]:
            assert len(group["key"]) == 4
            assert type(group["count"]) == int


class TestGroupBySizeParam:
    def test_group_by_size_param_underscore(self, client):
        res = client.get("/works?group-by=publication_year&group_by_size=10")
        json_data = res.get_json()
        assert len(json_data["group_by"]) == 10

    def test_group_by_size_param_hyphen(self, client):
        res = client.get("/works?group-by=publication_year&group-by-size=10")
        json_data = res.get_json()
        assert len(json_data["group_by"]) == 10

    def test_group_by_size_param_error(self, client):
        res = client.get("/works?group-by=publication_year&group-by-size=ff")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Param group-by-size must be a number."

    def test_group_by_size_exceeded(self, client):
        res = client.get("/works?group-by=publication_year&group-by-size=1000")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Group by size must be a number between 1 and 200"
        )
