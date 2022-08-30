class TestCounts:
    def test_counts(self, client):
        res = client.get("/counts")
        json_data = res.get_json()
        assert json_data == {
            "authors": 10000,
            "concepts": 10000,
            "institutions": 10000,
            "venues": 10000,
            "works": 10000,
        }
