class TestWorksIDGet:
    def test_works_openalex_get(self, client):
        res = client.get("/works/W2894744280")
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_openalex_get_case_insensitive(self, client):
        res = client.get("/works/w2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_openalex_get_url(self, client):
        res = client.get(
            "/works/https://openalex.org/W2894744280", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_openalex_get_key(self, client):
        res = client.get("/works/openalex:W2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_doi_get(self, client):
        res = client.get(
            "/works/https://doi.org/10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_doi_get_key(self, client):
        res = client.get(
            "/works/doi:10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_doi_get_partial_url(self, client):
        res = client.get(
            "/works/doi.org/10.1109/tbdata.2018.2872569", follow_redirects=True
        )
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_mag_get(self, client):
        res = client.get("/works/mag:2894744280", follow_redirects=True)
        json_data = res.get_json()
        assert json_data["id"] == "https://openalex.org/W2894744280"
        assert (
            json_data["display_name"]
            == "Fusing Location Data for Depression Prediction"
        )

    def test_works_id_get_bad_data(self, client):
        res = client.get("/works/2894744280", follow_redirects=True)
        assert res.status_code == 404
