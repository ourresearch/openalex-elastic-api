class TestAutoCompleteFilters:
    def test_autocomplete_filter_author_id(self, client):
        res = client.get("/autocomplete/works/filters/authorships.author.id?q=carl l")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "https://openalex.org/A1965815977",
            "display_value": "Carl Ludwig Siegel",
            "works_count": 1,
        }
        assert second_result == {
            "value": "https://openalex.org/A2997495481",
            "display_value": "Carl LoFaro",
            "works_count": 0,
        }

    def test_autocomplete_filter_institution_id(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.id?q=harv"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "https://openalex.org/I136199984",
            "display_value": "Harvard University",
            "works_count": 14,
        }
        assert second_result == {
            "value": "https://openalex.org/I133543626",
            "display_value": "Harvey Mudd College",
            "works_count": 0,
        }

    def test_autocomplete_filter_host_venue_display_name(self, client):
        res = client.get("/autocomplete/works/filters/host_venue.display_name?q=fa")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 10
        assert first_result == {
            "value": "https://openalex.org/V126771428",
            "display_value": "Family Medicine",
            "works_count": 2,
        }
        assert second_result == {
            "value": "https://openalex.org/V25293849",
            "display_value": "The FASEB Journal",
            "works_count": 0,
        }

    def test_autocomplete_filter_country_code(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.country_code?q=mo"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 7
        assert first_result == {
            "value": "MZ",
            "display_value": "Mozambique",
            "works_count": 3,
        }
        assert second_result == {
            "value": "MD",
            "display_value": "Moldova, Republic of",
            "works_count": 0,
        }

    def test_autocomplete_filter_publisher(self, client):
        res = client.get("/autocomplete/works/filters/host_venue.publisher?q=ra")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        third_result = json_data["filters"][2]
        assert len(json_data["filters"]) == 4
        assert first_result == {
            "value": "rand corporation",
            "display_value": "rand corporation",
            "works_count": 2,
        }
        assert third_result == {
            "value": "radiological society of north america",
            "display_value": "radiological society of north america",
            "works_count": 0,
        }

    def test_autocomplete_filter_institution_types_1_result(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.type?q=go"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "government",
            "display_value": "government",
            "works_count": 139,
        }

    def test_autocomplete_filter_institution_types_0_result(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.type?q=go&filter=publication_year:1750"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "government",
            "display_value": "government",
            "works_count": 0,
        }

    def test_autocomplete_filter_host_venue_license(self, client):
        res = client.get(
            "/autocomplete/works/filters/host_venue.license?q=cc&filter=publication_year:2020"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        third_result = json_data["filters"][2]
        assert len(json_data["filters"]) == 7
        assert first_result == {
            "value": "cc-by",
            "display_value": "cc-by",
            "works_count": 2,
        }
        assert third_result == {
            "value": "cc-by-nc-nd",
            "display_value": "cc-by-nc-nd",
            "works_count": 0,
        }

    def test_autocomplete_filter_host_venue_type_1_result(self, client):
        res = client.get("/autocomplete/works/filters/host_venue.type?q=re")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "repository",
            "display_value": "repository",
            "works_count": 221,
        }

    def test_autocomplete_filter_host_venue_type_0_result(self, client):
        res = client.get(
            "/autocomplete/works/filters/host_venue.type?q=re&filter=publication_year:1420"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "repository",
            "display_value": "repository",
            "works_count": 0,
        }

    def test_autocomplete_filter_type_1_result(self, client):
        res = client.get("/autocomplete/works/filters/type?q=jo")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "journal-article",
            "display_value": "journal-article",
            "works_count": 2884,
        }

    def test_autocomplete_filter_type_0_result(self, client):
        res = client.get(
            "/autocomplete/works/filters/type?q=jo&filter=publication_year:1420"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "journal-article",
            "display_value": "journal-article",
            "works_count": 0,
        }

    def test_autocomplete_filter_oa_status_1_result(self, client):
        res = client.get("/autocomplete/works/filters/open_access.oa_status?q=gr")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "green",
            "display_value": "green",
            "works_count": 222,
        }

    def test_autocomplete_filter_oa_status_0_result(self, client):
        res = client.get(
            "/autocomplete/works/filters/open_access.oa_status?q=gr&filter=publication_year:1420"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "green",
            "display_value": "green",
            "works_count": 0,
        }

    def test_autocomplete_filter_years(self, client):
        res = client.get("/autocomplete/works/filters/publication_year?q=182")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 10
        assert first_result == {
            "value": "1823",
            "display_value": "1823",
            "works_count": 2,
        }
        assert second_result == {
            "value": "1829",
            "display_value": "1829",
            "works_count": 0,
        }

    def test_autocomplete_filter_has_abstract(self, client):
        res = client.get(
            "/autocomplete/works/filters/has_abstract?filter=publication_year:2001"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "true",
            "display_value": "true",
            "works_count": 0,
        }
        assert second_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 213,
        }
