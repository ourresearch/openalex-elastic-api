class TestAuthorsSearch:
    def test_authors_search(self, client):
        res = client.get("/authors?search=jones")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 0
        assert "jones" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jones" in result["display_name"].lower()

    def test_authors_search_display_name(self, client):
        res = client.get("/authors?filter=display_name.search:jones")
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 0
        assert "jones" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jones" in result["display_name"].lower()

    def test_authors_search_exact(self, client):
        res = client.get("/authors?filter=display_name:Peter Vandenabeele")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Peter Vandenabeele"


class TestAuthorWorksCountFilter:
    def test_authors_works_count_equal(self, client):
        res = client.get("/authors?filter=works_count:50")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 12
        for result in json_data["results"][:25]:
            assert result["works_count"] == 50

    def test_authors_works_count_greater_than(self, client):
        res = client.get("/authors?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 102
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_authors_works_count_less_than(self, client):
        res = client.get("/authors?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9897
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_authors_works_count_range(self, client):
        res = client.get("/authors?filter=works_count:200-201")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["works_count"] == 200 or result["works_count"] == 201

    def test_authors_works_count_error(self, client):
        res = client.get("/authors?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestAuthorsCitedByCountFilter:
    def test_authors_cited_by_count_equal(self, client):
        res = client.get("/authors?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 34
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_authors_cited_by_count_greater_than(self, client):
        res = client.get("/authors?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3005
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_authors_cited_by_count_less_than(self, client):
        res = client.get("/authors?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6961
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_authors_cited_by_count_error(self, client):
        res = client.get("/authors?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestAuthorsLastKnownInstitution:
    def test_authors_last_known_institution_id_short(self, client):
        res = client.get("/authors?filter=last_known_institution.id:i32597200")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert (
                result["last_known_institution"]["id"]
                == "https://openalex.org/I32597200"
            )

    def test_authors_last_known_institution_id_long(self, client):
        res = client.get(
            "/authors?filter=last_known_institution.id:https://openalex.org/I32597200"
        )
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert (
                result["last_known_institution"]["id"]
                == "https://openalex.org/I32597200"
            )

    def test_authors_last_known_institution_ror(self, client):
        res = client.get(
            "/authors?filter=last_known_institution.ror:https://ror.org/00cv9y106"
        )
        json_data = res.get_json()
        assert (
            json_data["results"][0]["last_known_institution"]["ror"]
            == "https://ror.org/00cv9y106"
        )

    def test_authors_last_known_institution_country_code_single(self, client):
        res = client.get("/authors?filter=last_known_institution.country_code:us")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert result["last_known_institution"]["country_code"] == "US"

    def test_authors_last_known_institution_type(self, client):
        res = client.get("/authors?filter=last_known_institution.type:EducAtion")
        json_data = res.get_json()
        assert len(json_data["results"]) > 0
        for result in json_data["results"][:25]:
            assert result["last_known_institution"]["type"] == "education"


class TestAuthorsXConceptsID:
    count = 3227

    def test_authors_x_concepts_id_short(self, client):
        res = client.get("/authors?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_authors_x_concepts_id_long(self, client):
        res = client.get(
            "/authors?filter=x_concepts.id:https://openalex.org/c185592680"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_authors_concepts_id_alias_1(self, client):
        res = client.get("/authors?filter=concept.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_authors_concepts_id_alias_2(self, client):
        res = client.get("/authors?filter=concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestAuthorsExternalIDs:
    def test_authors_has_orcid_true(self, client):
        res = client.get("/authors?filter=has_orcid:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 826
        for result in json_data["results"][:25]:
            assert result["ids"]["orcid"] is not None

    def test_authors_has_orcid_false(self, client):
        res = client.get("/authors?filter=has_orcid:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9174
        for result in json_data["results"][:25]:
            assert "orcid" not in result["ids"] or result["ids"]["orcid"] is None

    def test_authors_has_orcid_error(self, client):
        res = client.get("/authors?filter=has_orcid:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for has_orcid must be true or false, not stt."
        )


class TestAuthorsMultipleIDs:
    def test_authors_openalex_single_long(self, client):
        res = client.get("/authors?filter=openalex_id:https://openalex.org/A2609699")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/A2609699"

    def test_authors_openalex_multiple_long(self, client):
        res = client.get(
            "/authors?filter=openalex_id:https://openalex.org/A2609699|https://openalex.org/A1389213"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/A2609699"
        assert json_data["results"][1]["id"] == "https://openalex.org/A1389213"

    def test_authors_openalex_single_short(self, client):
        res = client.get("/authors?filter=openalex_id:a2609699")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/A2609699"

    def test_authors_openalex_multiple_short(self, client):
        res = client.get("/authors?filter=openalex_id:A2609699|A1389213")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/A2609699"
        assert json_data["results"][1]["id"] == "https://openalex.org/A1389213"

    def test_authors_orcid_single_long(self, client):
        res = client.get("/authors?filter=orcid:https://orcid.org/0000-0001-5285-9835")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["orcid"] == "https://orcid.org/0000-0001-5285-9835"
        )

    def test_authors_orcid_single_short(self, client):
        res = client.get("/authors?filter=orcid:0000-0001-5285-9835")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["orcid"] == "https://orcid.org/0000-0001-5285-9835"
        )

    def test_authors_orcid_multiple(self, client):
        res = client.get(
            "/authors?filter=orcid:https://orcid.org/0000-0001-5285-9835|https://orcid.org/0000-0002-6276-3951"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert (
            json_data["results"][0]["orcid"] == "https://orcid.org/0000-0001-5285-9835"
        )
        assert (
            json_data["results"][1]["orcid"] == "https://orcid.org/0000-0002-6276-3951"
        )


class TestAuthorsOrder:
    def test_authors_primary_key_count(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert len(result.keys()) == 13

    def test_authors_order_of_primary_keys(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]
        expected_keys = [
            "id",
            "orcid",
            "display_name",
            "display_name_alternatives",
            "works_count",
            "cited_by_count",
            "ids",
            "last_known_institution",
            "x_concepts",
            "counts_by_year",
            "works_api_url",
            "updated_date",
            "created_date",
        ]
        actual_keys = result.keys()
        for expected_key, actual_key in zip(expected_keys, actual_keys):
            assert expected_key == actual_key

    def test_authors_last_known_institution_key_count(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]["last_known_institution"]
        assert len(result.keys()) == 5

    def test_authors_order_of_last_known_institution_keys(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]["last_known_institution"]
        expected_keys = ["id", "ror", "display_name", "country_code", "type"]
        actual_keys = result.keys()
        for expected_key, actual_key in zip(expected_keys, actual_keys):
            assert expected_key == actual_key

    def test_authors_x_concepts_key_count(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]["x_concepts"][0]
        assert len(result.keys()) == 5

    def test_authors_order_of_x_concepts_keys(self, client):
        res = client.get("/authors")
        json_data = res.get_json()
        result = json_data["results"][0]["x_concepts"][0]
        expected_keys = ["id", "wikidata", "display_name", "level", "score"]
        actual_keys = result.keys()
        for expected_key, actual_key in zip(expected_keys, actual_keys):
            assert expected_key == actual_key


class TestPeopleAlias:
    def test_people_alias(self, client):
        res = client.get("/people")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000


class TestAuthorsSelect:
    def test_authors_select_two_fields(self, client):
        res = client.get("/authors?select=display_name,orcid")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert len(result.keys()) == 2
        assert "display_name" in result.keys()
        assert "orcid" in result.keys()

    def test_authors_select_with_search(self, client):
        res = client.get("/authors?select=display_name,relevance_score&search=albert")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert len(result.keys()) == 2
        assert "display_name" in result.keys()
        assert "relevance_score" in result.keys()
        assert isinstance(result["relevance_score"], float)

    def test_authors_select_with_filter(self, client):
        res = client.get(
            "/authors?select=display_name,orcid&filter=orcid:0000-0001-5285-9835"
        )
        json_data = res.get_json()
        result = json_data["results"][0]
        assert len(result.keys()) == 2
        assert "display_name" in result.keys()
        assert "orcid" in result.keys()
