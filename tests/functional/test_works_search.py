class TestWorksSearch:
    def test_works_search(self, client):
        res = client.get("/works?search=analysis")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1396
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
        assert json_data["meta"]["count"] == 211
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

    def test_works_search_not_operator_error(self, client):
        res = client.get("/works?search=!zoo")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == (
            "The search parameter does not support the ! operator. Problem value: !zoo"
        )

    def test_works_search_pipe_operator_error(self, client):
        res = client.get("/works?search=dna|rna")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == (
            "The search parameter does not support the | operator. Problem value: dna|rna"
        )

    def test_works_filter_search_not_operator_error(self, client):
        res = client.get("/works?filter=abstract.search:!zoo")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == (
            "Search filters do not support the ! operator. Problem value: !zoo"
        )

    def test_works_search_wildcard(self, client):
        res = client.get("/works?search=analys*")
        assert res.status_code == 200

    def test_works_filter_search_wildcard(self, client):
        res = client.get("/works?filter=display_name.search:analys*")
        assert res.status_code == 200
