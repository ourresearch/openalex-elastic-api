class TestWorksSearch:
    def test_works_search(self, client):
        res = client.get("/works?search=analysis")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 219
        assert "analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "analysis" in result["display_name"].lower()

    def test_works_search_blank(self, client):
        res = client.get('/works?search=""')
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000

    def test_works_search_display_name(self, client):
        res = client.get("/works?filter=display_name.search:analysis")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 219
        assert "analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "analysis" in result["display_name"].lower()

    def test_works_search_alias(self, client):
        res = client.get("/works?filter=title.search:factor%20analysis")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            display_name = result["display_name"].lower()
            assert (
                "factor" in display_name or "factors" in display_name
            ) and "analysis" in display_name

    def test_works_search_phrase(self, client):
        res = client.get('/works?filter=title.search:"factor%20analysis"')
        json_data = res.get_json()
        assert "factor analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "factor analysis" in result["display_name"].lower()

    def test_works_search_exact(self, client):
        res = client.get(
            "/works?filter=display_name:Fusing Location Data for Depression Prediction"
        )
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["display_name"]
                == "Fusing Location Data for Depression Prediction"
            )

    def test_works_search_abstract(self, client):
        res = client.get("/works?filter=abstract.search:zoo keeper")
        assert res.status_code == 200
