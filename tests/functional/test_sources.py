class TestSourcesSearch:
    def test_sources_search(self, client):
        res = client.get("/sources?search=university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_sources_search_additional_fields(self, client):
        """Search across display_name, alternate_titles, and abbreviated_title."""
        res = client.get("/sources?search=jasa")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["display_name"]
            == "Jurnal manajemen dan pemasaran jasa"
        )

    def test_sources_search_display_name(self, client):
        res = client.get("/sources?filter=display_name.search:university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_sources_search_exact(self, client):
        res = client.get("/sources?filter=display_name:The Lancet")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"] == "The Lancet"


class TestSourcesWorksCountFilter:
    def test_sources_works_count_equal(self, client):
        res = client.get("/sources?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_sources_works_count_greater_than(self, client):
        res = client.get("/sources?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4152
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_sources_works_count_less_than(self, client):
        res = client.get("/sources?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5826
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_sources_works_count_error(self, client):
        res = client.get("/sources?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestSourcesCitedByCountFilter:
    def test_sources_cited_by_count_equal(self, client):
        res = client.get("/sources?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 29
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_sources_cited_by_count_greater_than(self, client):
        res = client.get("/sources?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8224
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_sources_cited_by_count_less_than(self, client):
        res = client.get("/sources?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1747
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_sources_cited_by_count_range(self, client):
        res = client.get("/sources?filter=cited_by_count:20-21")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 68
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20 or result["cited_by_count"] == 21

    def test_sources_cited_by_count_error(self, client):
        res = client.get("/sources?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestSourcesXConceptsIDFilter:
    count = 2448

    def test_sources_x_concepts_id_short(self, client):
        res = client.get("/sources?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_sources_x_concepts_id_long(self, client):
        res = client.get(
            "/sources?filter=x_concepts.id:https://openalex.org/c185592680"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_sources_x_concepts_id_alias_1(self, client):
        res = client.get("/sources?filter=concept.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_sources_x_concepts_id_alias_2(self, client):
        res = client.get("/sources?filter=concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestSourcesOAFilters:
    def test_sources_is_oa(self, client):
        res = client.get("/sources?filter=is_oa:TRue")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1710
        for result in json_data["results"][:25]:
            assert result["is_oa"] == True

    def test_sources_is_in_doaj(self, client):
        res = client.get("/sources?filter=is_in_doaj:FaLse")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3680
        for result in json_data["results"][:25]:
            assert result["is_in_doaj"] == False


class TestSourcesPublisher:
    def test_sources_publisher_single(self, client):
        res = client.get("/sources?filter=publisher:cambridge University press")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 42
        for result in json_data["results"]:
            assert result["publisher"] == "Cambridge University Press"


class TestSourcesExternalIDs:
    def test_sources_has_issn_true(self, client):
        res = client.get("/sources?filter=has_issn:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5408
        for result in json_data["results"][:25]:
            assert result["ids"]["issn"] is not None

    def test_sources_has_issn_false(self, client):
        res = client.get("/sources?filter=has_issn:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4592
        for result in json_data["results"][:25]:
            assert "issn" not in result["ids"] or result["ids"]["issn"] is None

    def test_sources_has_issn_error(self, client):
        res = client.get("/sources?filter=has_issn:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for has_issn must be true or false, not stt."
        )


class TestSourcesMultipleIDs:
    def test_sources_openalex_multiple_long(self, client):
        res = client.get(
            "/sources?filter=openalex_id:https://openalex.org/S4306462995|https://openalex.org/S49861241"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/S4306462995"
        assert json_data["results"][1]["id"] == "https://openalex.org/S49861241"

    def test_sources_issn_single(self, client):
        res = client.get("/sources?filter=issn:0140-6736")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert "0140-6736" in json_data["results"][0]["issn"]

    def test_concepts_wikidata_multiple(self, client):
        res = client.get("/sources?filter=issn:0099-5355|0036-8075")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert "0099-5355" in json_data["results"][0]["issn"]
        assert "0036-8075" in json_data["results"][1]["issn"]


class TestSourcesType:
    def test_sources_type_single(self, client):
        res = client.get("/sources?filter=type:joUrnal")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8548
        for result in json_data["results"]:
            assert result["type"] == "journal"

    def test_sources_type_not(self, client):
        res = client.get("/sources?filter=type:!journal")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1452
        for result in json_data["results"]:
            assert "type" not in result or result["type"] != "journal"

    def test_sources_type_group_by(self, client):
        res = client.get("/sources?group-by=type")
        json_data = res.get_json()
        assert json_data["group_by"][0] == {
            "key": "journal",
            "key_display_name": "journal",
            "count": 8548,
        }


class TestSourcesCountryCode:
    def test_sources_country_code_single(self, client):
        res = client.get("/sources?filter=country_code:uS")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 777
        for result in json_data["results"]:
            assert result["country_code"] == "US"

    def test_sources_country_code_not(self, client):
        res = client.get("/sources?filter=country_code:!us")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9223
        for result in json_data["results"]:
            assert "country_code" not in result or result["country_code"] != "US"

    def test_sources_country_code_group_by(self, client):
        res = client.get("/sources?group-by=country_code")
        json_data = res.get_json()
        assert json_data["group_by"][0] == {
            "count": 5204,
            "key": "unknown",
            "key_display_name": "unknown",
        }
        assert json_data["group_by"][1] == {
            "count": 777,
            "key": "US",
            "key_display_name": "United States of America",
        }


class TestRelevanceScore:
    def test_relevance_hidden(self, client):
        res = client.get("/sources")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" not in result

    def test_relevance_displayed_filter_search(self, client):
        res = client.get("/sources?filter=display_name.search:nature")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" in result
        assert result["relevance_score"] > 0.0

    def test_relevance_displayed_regular_search(self, client):
        res = client.get("/sources?search=nature")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" in result


class TestRaiseError:
    def test_error_or_query_between_filters(self, client):
        res = client.get("/sources?filter=has_issn:false|works_count:>100")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "It looks like you're trying to do an OR query between filters and it's not supported. \nYou can do this: institutions.country_code:fr|en, but not this: institutions.country_code:gb|host_venue.issn:0957-1558. \nProblem value: false|works_count:>100"
        )


class TestJournalsAlias:
    def test_journals_alias(self, client):
        res = client.get("/journals")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000


class TestSourcesMagId:
    def test_sources_mag_id_single(self, client):
        res = client.get("/sources?filter=ids.mag:49861241")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/S49861241"


class TestOpenAlexId:
    def test_sources_openalex_id_single(self, client):
        res = client.get("/sources?filter=ids.openalex:S49861241")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/S49861241"


class TestSourcesSelect:
    def test_sources_select(self, client):
        res = client.get("/sources?select=id,display_name")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000
        for result in json_data["results"]:
            assert len(result) == 2
            assert "id" in result
            assert "display_name" in result

    def test_sources_select_error(self, client):
        res = client.get("/sources?select=display_name,not_a_field")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert "not_a_field is not a valid select field" in json_data["message"]

    def test_sources_group_by_select_error(self, client):
        res = client.get("/sources?group-by=type&select=display_name")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "select does not work with group_by."
