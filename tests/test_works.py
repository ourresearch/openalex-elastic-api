class TestWorksPublicationYearFilter:
    def test_works_publication_year(self, client):
        res = client.get("/works?filter=publication_year:2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 27
        assert json_data["results"][0]["id"] == "https://openalex.org/W2894716986"
        assert json_data["results"][0]["cited_by_count"] == 4
        assert res.status_code == 200

    def test_works_publication_year_greater_than(self, client):
        res = client.get("/works?filter=publication_year:>2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_year_less_than(self, client):
        res = client.get("/works?filter=publication_year:<2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9966
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893871524"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_year_error(self, client):
        res = client.get("/works?filter=publication_year:ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param publication_year must be a number."
        )


class TestWorksPublicationDateFilter:
    def test_works_publication_date(self, client):
        res = client.get("/works?filter=publication_date:2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        assert json_data["results"][0]["id"] == "https://openalex.org/W2895362161"
        assert json_data["results"][0]["cited_by_count"] == 7
        assert res.status_code == 200

    def test_works_publication_date_greater_than(self, client):
        res = client.get("/works?filter=publication_date:>2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 30
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_date_less_than(self, client):
        res = client.get("/works?filter=publication_date:<2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9966
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893871524"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_date_error(self, client):
        res = client.get("/works?filter=publication_date:2020-01-555")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param publication_date must be a date in format 2020-05-17."
        )


class TestWorksHostVenueFilter:
    def test_works_host_venue_issn(self, client):
        res = client.get("/works?filter=host_venue.issn:2332-7790")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"]:
            assert "2332-7790" in result["host_venue"]["issn"]

    def test_works_host_venue_publisher(self, client):
        res = client.get("/works?filter=host_venue.publisher:ElseVier Bv")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 36
        for result in json_data["results"]:
            assert result["host_venue"]["publisher"] == "Elsevier BV"

    def test_works_host_venue_id_short(self, client):
        res = client.get("/works?filter=host_venue.id:v2898264183")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["publication_date"] == "2019-09-01"
        assert (
            json_data["results"][0]["host_venue"]["display_name"]
            == "Health Professions Education"
        )
        assert json_data["results"][0]["host_venue"]["publisher"] == "Elsevier BV"
        assert res.status_code == 200

    def test_works_host_venue_id_long(self, client):
        res = client.get("/works?filter=host_venue.id:https://openalex.org/v2898264183")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["publication_date"] == "2019-09-01"
        assert (
            json_data["results"][0]["host_venue"]["display_name"]
            == "Health Professions Education"
        )
        assert json_data["results"][0]["host_venue"]["publisher"] == "Elsevier BV"
        assert res.status_code == 200


class TestWorksTypeFilter:
    def test_works_type(self, client):
        res = client.get("/works?filter=type:journAl-arTicle")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2884
        for result in json_data["results"][:25]:
            assert result["type"] == "journal-article"
