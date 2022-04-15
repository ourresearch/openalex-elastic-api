class TestInstitutionsSearch:
    def test_institutions_search(self, client):
        res = client.get("/institutions?search=university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_institutions_search_display_name(self, client):
        res = client.get("/institutions?filter=display_name.search:university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_institutions_search_exact(self, client):
        res = client.get(
            "/institutions?filter=display_name:Chinese Academy of Sciences"
        )
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"] == "Chinese Academy of Sciences"


class TestInstitutionsWorksCountFilter:
    def test_institutions_works_count_equal(self, client):
        res = client.get("/institutions?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_institutions_works_count_greater_than(self, client):
        res = client.get("/institutions?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6712
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_institutions_works_count_less_than(self, client):
        res = client.get("/institutions?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3279
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_institutions_works_count_error(self, client):
        res = client.get("/institutions?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestInstitutionsCitedByCountFilter:
    def test_institutions_cited_by_count_equal(self, client):
        res = client.get("/institutions?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_institutions_cited_by_count_greater_than(self, client):
        res = client.get("/institutions?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9914
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_institutions_cited_by_count_less_than(self, client):
        res = client.get("/institutions?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 82
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_institutions_cited_by_count_error(self, client):
        res = client.get("/institutions?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestInstitutionsXConceptsIDFilter:
    def test_institutions_x_concepts_id_short(self, client):
        res = client.get("/institutions?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_institutions_x_concepts_id_long(self, client):
        res = client.get(
            "/institutions?filter=x_concepts.id:https://openalex.org/c185592680"
        )
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestInstitutionsCountryCodeFilter:
    def test_institutions_country_code(self, client):
        res = client.get("/institutions?filter=country_code:us")
        json_data = res.get_json()
        assert json_data["results"][0]["country_code"].lower() == "us"
        for result in json_data["results"][:25]:
            assert result["country_code"].lower() == "us"


class TestInstitutionsTypeFilter:
    def test_institutions_type(self, client):
        res = client.get("/institutions?filter=type:education")
        json_data = res.get_json()
        assert json_data["results"][0]["type"].lower() == "education"
        for result in json_data["results"][:25]:
            assert result["type"].lower() == "education"


class TestInstitutionsExternalIDs:
    def test_institutions_has_ror_true(self, client):
        res = client.get("/institutions?filter=has_ror:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7220
        for result in json_data["results"][:25]:
            assert result["ids"]["ror"] is not None

    def test_institutions_has_ror_false(self, client):
        res = client.get("/institutions?filter=has_ror:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2780
        for result in json_data["results"][:25]:
            assert result["ids"]["ror"] is None

    def test_institutions_has_ror_error(self, client):
        res = client.get("/institutions?filter=has_ror:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for has_ror must be true or false, not stt."
        )


class TestInstitutionsMultipleIDs:
    def test_Institutions_openalex_multiple_long(self, client):
        res = client.get(
            "/institutions?filter=openalex_id:https://openalex.org/I19820366|https://openalex.org/I136199984"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/I19820366"
        assert json_data["results"][1]["id"] == "https://openalex.org/I136199984"

    def test_institutions_ror_single_long(self, client):
        res = client.get("/institutions?filter=ror:https://ror.org/034t30j35")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["ror"] == "https://ror.org/034t30j35"

    def test_institutions_ror_single_short(self, client):
        res = client.get("/institutions?filter=ror:034t30j35")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["ror"] == "https://ror.org/034t30j35"

    def test_institutions_ror_multiple(self, client):
        res = client.get(
            "/institutions?filter=ror:https://ror.org/034t30j35|https://ror.org/03vek6s52"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["ror"] == "https://ror.org/034t30j35"
        assert json_data["results"][1]["ror"] == "https://ror.org/03vek6s52"
