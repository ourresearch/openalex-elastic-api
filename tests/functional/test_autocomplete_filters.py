class TestAutoCompleteFilters:
    def test_autocomplete_filter_author_id(self, client):
        res = client.get("/autocomplete/works/filters/authorships.author.id?q=carl c")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "https://openalex.org/A2236313142",
            "display_value": "Carl E. Cerniglia",
            "works_count": 1,
        }
        assert second_result == {
            "value": "https://openalex.org/A2660293885",
            "display_value": "Carl T. Chase",
            "works_count": 1,
        }

    def test_autocomplete_filter_institution_id(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.id?q=harv"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "https://openalex.org/I136199984",
            "display_value": "Harvard University",
            "works_count": 14,
        }

    def test_autocomplete_filter_host_venue_display_name(self, client):
        res = client.get("/autocomplete/works/filters/host_venue.id?q=fa")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        second_result = json_data["filters"][1]
        assert len(json_data["filters"]) == 10
        assert first_result == {
            "value": "https://openalex.org/V25293849",
            "display_value": "The FASEB Journal",
            "works_count": 18,
        }
        assert second_result == {
            "value": "https://openalex.org/V72111607",
            "display_value": "Canadian Family Physician",
            "works_count": 3,
        }

    def test_autocomplete_filter_country_code(self, client):
        res = client.get(
            "/autocomplete/works/filters/authorships.institutions.country_code?q=mo"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "MZ",
            "display_value": "Mozambique",
            "works_count": 3,
        }

    def test_autocomplete_filter_publisher(self, client):
        res = client.get("/autocomplete/works/filters/host_venue.publisher?q=ra")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        third_result = json_data["filters"][2]
        assert len(json_data["filters"]) == 10
        assert first_result == {
            "value": "amsterdam: raap archeologisch adviesbureau",
            "display_value": "amsterdam: raap archeologisch adviesbureau",
            "works_count": 2,
        }
        assert third_result == {
            "value": "weesp: raap archeologisch adviesbureau",
            "display_value": "weesp: raap archeologisch adviesbureau",
            "works_count": 2,
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

    def test_autocomplete_filter_host_venue_license(self, client):
        res = client.get(
            "/autocomplete/works/filters/host_venue.license?q=cc&filter=publication_year:2020"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "cc-by",
            "display_value": "cc-by",
            "works_count": 2,
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

    def test_autocomplete_filter_years(self, client):
        res = client.get("/autocomplete/works/filters/publication_year?q=182")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "1823",
            "display_value": "1823",
            "works_count": 2,
        }

    def test_autocomplete_filter_has_abstract(self, client):
        res = client.get(
            "/autocomplete/works/filters/has_abstract?filter=publication_year:2001"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 213,
        }

    def test_autocomplete_filter_has_doi(self, client):
        res = client.get(
            "/autocomplete/works/filters/has_doi?filter=publication_year:1919"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 1,
        }

    def test_autocomplete_filter_has_ngrams(self, client):
        res = client.get(
            "/autocomplete/works/filters/has_ngrams?filter=publication_year:1917"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 2,
        }

    def test_autocomplete_filter_is_paratext(self, client):
        res = client.get("/autocomplete/works/filters/is_paratext")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 3332,
        }

    def test_autocomplete_filter_is_retracted(self, client):
        res = client.get("/autocomplete/works/filters/is_retracted")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "false",
            "display_value": "false",
            "works_count": 10000,
        }

    def test_autocomplete_filter_oa_status(self, client):
        res = client.get(
            "/autocomplete/works/filters/open_access.is_oa?filter=publication_year:1947"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "true",
            "display_value": "true",
            "works_count": 2,
        }

    def test_autocomplete_filter_concept_ids(self, client):
        res = client.get("/autocomplete/works/filters/concepts.id?q=scie")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 8
        assert first_result == {
            "value": "https://openalex.org/C41008148",
            "display_value": "Computer science",
            "works_count": 1411,
        }

    def test_autocomplete_filter_alternate_host_venue_id(self, client):
        res = client.get("/autocomplete/works/filters/alternate_host_venues.id?q=natio")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "https://openalex.org/V2764393826",
            "display_value": "National Journal of Clinical Anatomy",
            "works_count": 1,
        }

    def test_autocomplete_filter_host_venue_license(self, client):
        res = client.get(
            "/autocomplete/works/filters/host_venue.license?q=cc&filter=publication_year:2020"
        )
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 2
        assert first_result == {
            "value": "cc-by",
            "display_value": "cc-by",
            "works_count": 2,
        }

    def test_autocomplete_filter_alternate_host_venue_type_1_result(self, client):
        res = client.get("/autocomplete/works/filters/alternate_host_venues.type?q=re")
        json_data = res.get_json()
        first_result = json_data["filters"][0]
        assert len(json_data["filters"]) == 1
        assert first_result == {
            "value": "repository",
            "display_value": "repository",
            "works_count": 324,
        }
