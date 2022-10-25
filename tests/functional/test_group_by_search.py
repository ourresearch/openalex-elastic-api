class TestGroupBySearch:
    def test_group_by_search_author_id(self, client):
        res = client.get("/works?group-by=author.id&q=a")
        json_data = res.get_json()
        first_result = json_data["group_by"][0]
        assert len(json_data["group_by"]) == 1
        assert first_result == {
            "key": "https://openalex.org/A1382709",
            "key_display_name": "Alejandro López-Ortiz",
            "count": 1,
        }

    def test_group_by_institutions_id(self, client):
        res = client.get("/works?group-by=institutions.id&q=har")
        json_data = res.get_json()
        first_result = json_data["group_by"][0]
        assert len(json_data["group_by"]) == 3
        assert first_result == {
            "key": "https://openalex.org/I136199984",
            "key_display_name": "Harvard University",
            "count": 21,
        }
