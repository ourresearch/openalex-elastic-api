import country_list


class TestWorksContinentsFilters:
    def test_works_continent_africa(self, client):
        res = client.get("/works?filter=institutions.continent:africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 50 and json_data["meta"]["count"] < 150

    def test_works_continent_not_africa(self, client):
        res = client.get("/works?filter=institutions.continent:!africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 9500 and json_data["meta"]["count"] < 9980

    def test_works_continent_africa_code_lower(self, client):
        res = client.get("/works?filter=authorships.institutions.continent:q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 50 and json_data["meta"]["count"] < 150

    def test_works_continent_not_africa_code(self, client):
        res = client.get("/works?filter=authorships.institutions.continent:!Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 9500 and json_data["meta"]["count"] < 9980

    def test_works_continent_africa_code_upper(self, client):
        res = client.get("/works?filter=institutions.continent:Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 50 and json_data["meta"]["count"] < 150

    def test_works_continent_asia(self, client):
        res = client.get("/works?filter=authorships.institutions.continent:asia")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 500 and json_data["meta"]["count"] < 700

    def test_works_continent_asia_alias_1(self, client):
        res = client.get("/works?filter=institutions.continent:asia")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 500 and json_data["meta"]["count"] < 700

    def test_works_continent_europe_mixed_case(self, client):
        res = client.get("/works?filter=institutions.continent:EuropE")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 800 and json_data["meta"]["count"] < 1200

    def test_works_continent_europe_code(self, client):
        res = client.get("/works?filter=institutions.continent:Q46")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 900 and json_data["meta"]["count"] < 1200

    def test_works_continent_north_america(self, client):
        res = client.get("/works?filter=institutions.continent:north_america")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 800 and json_data["meta"]["count"] < 1200

    def test_works_continent_north_america_code(self, client):
        res = client.get("/works?filter=institutions.continent:Q49")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 800 and json_data["meta"]["count"] < 1200

    def test_works_continent_oceania(self, client):
        res = client.get("/works?filter=institutions.continent:ocEania")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 50 and json_data["meta"]["count"] < 100

    def test_works_continent_oceania_code(self, client):
        res = client.get("/works?filter=institutions.continent:q55643&per-page=50")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 50 and json_data["meta"]["count"] < 100
        # ensure every work has at least one author institution in Oceania
        oceania_country_codes = [
            c["country_code"] for c in country_list.COUNTRIES_BY_CONTINENT["Oceania"]
        ]
        for work in json_data["results"]:
            country_found = False
            for author in work["authorships"]:
                for institution in author["institutions"]:
                    if institution["country_code"] in oceania_country_codes:
                        country_found = True
                        break
            assert country_found

    def test_works_continent_south_america(self, client):
        res = client.get("/works?filter=institutions.continent:south_america")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 100 and json_data["meta"]["count"] < 150

    def test_works_continent_south_america_code(self, client):
        res = client.get("/works?filter=institutions.continent:Q18")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 100 and json_data["meta"]["count"] < 150


class TestWorksGlobalSouthFilter:
    def test_works_global_south(self, client):
        res = client.get(
            "/works?filter=authorships.institutions.is_global_south:true&per-page=50"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 500 and json_data["meta"]["count"] < 700
        # ensure every work has at least one author institution in Oceania
        global_south_country_codes = [
            c["country_code"] for c in countries.GLOBAL_SOUTH_COUNTRIES
        ]
        for work in json_data["results"]:
            country_found = False
            for author in work["authorships"]:
                for institution in author["institutions"]:
                    if institution["country_code"] in global_south_country_codes:
                        country_found = True
                        break
            assert country_found

    def test_works_global_south_alias_1(self, client):
        res = client.get("/works?filter=institutions.is_global_south:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 500 and json_data["meta"]["count"] < 700

    def test_works_global_south_false(self, client):
        res = client.get("/works?filter=institutions.is_global_south:False")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 9000 and json_data["meta"]["count"] < 9800


class TestWorksContinentsGroupBy:
    def test_works_continent_group_by_primary(self, client):
        res = client.get("/works?group_by=authorships.institutions.continent")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8
        assert json_data["group_by"][1] == {
            "key": "Q46",
            "key_display_name": "Europe",
            "count": 1027,
        }

    def test_works_continent_group_by_alias_1(self, client):
        res = client.get("/works?group_by=institutions.continent")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8
        assert json_data["group_by"][1] == {
            "key": "Q46",
            "key_display_name": "Europe",
            "count": 1027,
        }


class TestWorksGlobalSouthGroupBy:
    def test_works_global_south_group_by(self, client):
        res = client.get("/works?group_by=institutions.is_global_south")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["group_by"] == [
            {"key": "true", "key_display_name": "true", "count": 632},
            {"key": "false", "key_display_name": "false", "count": 9368},
        ]

    def test_works_global_south_group_by_alias_1(self, client):
        res = client.get("/works?group_by=authorships.institutions.is_global_south")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["group_by"] == [
            {"key": "true", "key_display_name": "true", "count": 632},
            {"key": "false", "key_display_name": "false", "count": 9368},
        ]


class TestInstitutionsContinentsFilters:
    def test_institutions_continent_africa(self, client):
        res = client.get("/institutions?filter=continent:africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 316

    def test_institutions_continent_not_africa(self, client):
        res = client.get("/institutions?filter=continent:!africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9684

    def test_institutions_continent_africa_code(self, client):
        res = client.get("/institutions?filter=continent:Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 316

    def test_institutions_continent_not_africa_code(self, client):
        res = client.get("/institutions?filter=continent:!Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9684

    def test_institutions_global_south(self, client):
        res = client.get("/institutions?filter=is_global_south:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2770


class TestInstitutionsContinentsGroupBy:
    def test_institutions_continent_group_by(self, client):
        res = client.get("/institutions?group_by=continent")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8
        assert json_data["group_by"][1] == {
            "key": "Q49",
            "key_display_name": "North America",
            "count": 3164,
        }

    def test_institutions_global_south_group_by(self, client):
        res = client.get("/institutions?group_by=is_global_south")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["group_by"] == [
            {"key": "true", "key_display_name": "true", "count": 2770},
            {"key": "false", "key_display_name": "false", "count": 7230},
        ]


class TestAuthorsContinentFilter:
    def test_authors_continent_europe(self, client):
        res = client.get("/authors?filter=last_known_institution.continent:Europe")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1970

    def test_authors_continent_not_europe(self, client):
        res = client.get("/authors?filter=last_known_institution.continent:!Europe")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8030

    def test_authors_continent_europe_code(self, client):
        res = client.get("/authors?filter=last_known_institution.continent:Q46")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1970

    def test_authors_continent_not_europe_code(self, client):
        res = client.get("/authors?filter=last_known_institution.continent:!Q46")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8030

    def test_authors_global_south_true(self, client):
        res = client.get("/authors?filter=last_known_institution.is_global_south:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1205

    def test_authors_global_south_false(self, client):
        res = client.get("/authors?filter=last_known_institution.is_global_south:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8795


class TestSourcesContinentsFilters:
    def test_sources_continent_africa(self, client):
        res = client.get("/sources?filter=continent:africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 128

    def test_sources_continent_not_africa(self, client):
        res = client.get("/sources?filter=continent:!africa")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9872

    def test_sources_continent_africa_code(self, client):
        res = client.get("/sources?filter=continent:Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 128

    def test_sources_continent_not_africa_code(self, client):
        res = client.get("/sources?filter=continent:!Q15")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9872

    def test_sources_global_south(self, client):
        res = client.get("/sources?filter=is_global_south:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1612


class TestSourcesContinentsGroupBy:
    def test_sources_continent_group_by(self, client):
        res = client.get("/sources?group_by=continent")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8
        assert json_data["group_by"][1] == {
            "key": "Q46",
            "key_display_name": "Europe",
            "count": 1896,
        }

    def test_sources_global_south_group_by(self, client):
        res = client.get("/sources?group_by=is_global_south")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["group_by"] == [
            {"key": "true", "key_display_name": "true", "count": 1612},
            {"key": "false", "key_display_name": "false", "count": 8388},
        ]
