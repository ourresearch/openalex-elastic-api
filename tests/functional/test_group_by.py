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


class TestGroupByPaginationErrors:
    def test_group_by_page_error(self, client):
        res = client.get("/works?group-by=publication_year&page=2")
        json_data = res.get_json()
        assert json_data["error"] == "Pagination error."
        assert (
            json_data["message"]
            == "Unable to paginate beyond page 1. Group-by is limited to page 1 with up to 200 results at this time."
        )


class TestGroupByNameKey:
    def test_group_by_unknown_regular(self, client):
        res = client.get("/works?group-by=host_venue.id")
        json_data = res.get_json()
        result = json_data["group_by"][0]
        assert result["key"] == "unknown"
        assert result["key_display_name"] == "unknown"
        assert result["count"] == 3376

    def test_group_by_known_filter(self, client):
        res = client.get("/works?group-by=host_venue.id:known")
        json_data = res.get_json()
        results = json_data["group_by"]
        for result in results:
            assert result["key"] != "unknown"

    def test_group_by_boolean(self, client):
        res = client.get("/venues?group_by=is_oa")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        assert result1["key"] == "false"
        assert result1["key_display_name"] == "false"
        assert result1["count"] == 6767
        result2 = json_data["group_by"][1]
        assert result2["key"] == "unknown"
        assert result2["key_display_name"] == "unknown"
        assert result2["count"] == 1882
        result3 = json_data["group_by"][2]
        assert result3["key"] == "true"
        assert result3["key_display_name"] == "true"
        assert result3["count"] == 1351

    def test_group_by_name_key(self, client):
        res = client.get("/works?group-by=host_venue.id")
        json_data = res.get_json()
        result = json_data["group_by"][4]
        assert result["key"] == "https://openalex.org/V106296714"
        assert result["key_display_name"] == None
        assert result["count"] == 47


class TestGroupByExternalIds:
    def test_group_by_has_orcid(self, client):
        res = client.get("/authors?group-by=has_orcid")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 826
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 9174

    def test_group_by_has_wikidata(self, client):
        res = client.get("/concepts?group-by=has_wikidata")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 9996
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 4

    def test_group_by_has_ror(self, client):
        res = client.get("/institutions?group-by=has_ror")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 7220
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 2780

    def test_group_by_has_issn(self, client):
        res = client.get("/venues?group-by=has_issn")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 8823
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 1177

    def test_group_by_has_doi(self, client):
        res = client.get("/works?group-by=has_doi")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 3718
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 6282

    def test_group_by_has_pmid(self, client):
        res = client.get("/works?group-by=has_pmid")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 998
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 9002

    def test_group_by_has_pmcid(self, client):
        res = client.get("/works?group-by=has_pmcid")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 247
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 9753


class TestGroupByVersion:
    def test_group_by_version(self, client):
        res = client.get("/works?group-by=version")
        json_data = res.get_json()
        assert json_data["group_by"] == [
            {"key": "null", "key_display_name": "null", "count": 8910},
            {
                "key": "publishedVersion",
                "key_display_name": "publishedVersion",
                "count": 881,
            },
            {
                "key": "submittedVersion",
                "key_display_name": "submittedVersion",
                "count": 354,
            },
            {
                "key": "acceptedVersion",
                "key_display_name": "acceptedVersion",
                "count": 61,
            },
        ]

    def test_group_by_host_venue_version(self, client):
        res = client.get("/works?group-by=host_venue.version")
        json_data = res.get_json()
        assert json_data["group_by"] == [
            {"key": "unknown", "key_display_name": "unknown", "count": 8992},
            {
                "key": "publishedVersion",
                "key_display_name": "publishedVersion",
                "count": 866,
            },
            {
                "key": "submittedVersion",
                "key_display_name": "submittedVersion",
                "count": 115,
            },
            {
                "key": "acceptedVersion",
                "key_display_name": "acceptedVersion",
                "count": 27,
            },
        ]
