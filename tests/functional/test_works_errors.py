class TestWorksInvalidFields:
    def test_works_invalid_publication_year(self, client):
        res = client.get("/works?filter=publication-yearrr:2020")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"].startswith(
            "publication_yearrr is not a valid field. Valid fields are underscore or hyphenated versions of:"
        )


class TestWorksMultipleFiltersError:
    def test_works_multiple_filters_error_v1(self, client):
        res = client.get(
            "/works?filter=has_oa_accepted_or_published_version:true&filter=has_oa_accepted_or_published_version:false"
        )
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Only one filter parameter is allowed. "
            "Your URL contains filters like: /works?filter=publication_year:2020&filter=is_open_access:true. "
            "Combine and separate filters with a comma, like: /works?filter=publication_year:2020,is_open_access:true."
        )

    def test_works_multiple_filters_error_v2(self, client):
        res = client.get(
            "/works?search=gray&filter=has_oa_accepted_or_published_version:true&filter=has_oa_accepted_or_published_version:false"
        )
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Only one filter parameter is allowed. "
            "Your URL contains filters like: /works?filter=publication_year:2020&filter=is_open_access:true. "
            "Combine and separate filters with a comma, like: /works?filter=publication_year:2020,is_open_access:true."
        )

    def test_works_multiple_filters_no_error(self, client):
        res = client.get("/works?search=filter=?filter=?filter=")
        assert res.status_code == 200
