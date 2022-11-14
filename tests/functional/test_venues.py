class TestVenuesSearch:
    def test_venues_search(self, client):
        res = client.get("/venues?search=university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_venues_search_additional_fields(self, client):
        """Search across display_name, alternate_titles, and abbreviated_title."""
        res = client.get("/venues?search=jasa")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["display_name"]
            == "Journal of the Acoustical Society of America"
        )

    def test_venues_search_display_name(self, client):
        res = client.get("/venues?filter=display_name.search:university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

    def test_venues_search_exact(self, client):
        res = client.get("/venues?filter=display_name:ChemInform")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"] == "ChemInform"


class TestVenuesWorksCountFilter:
    def test_venues_works_count_equal(self, client):
        res = client.get("/venues?filter=works_count:850")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_venues_works_count_greater_than(self, client):
        res = client.get("/venues?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8118
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_venues_works_count_less_than(self, client):
        res = client.get("/venues?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1882
        for result in json_data["results"][:25]:
            assert result["works_count"] < 200

    def test_venues_works_count_error(self, client):
        res = client.get("/venues?filter=works_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Value for param works_count must be a number."


class TestVenuesCitedByCountFilter:
    def test_venues_cited_by_count_equal(self, client):
        res = client.get("/venues?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_venues_cited_by_count_greater_than(self, client):
        res = client.get("/venues?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9092
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_venues_cited_by_count_less_than(self, client):
        res = client.get("/venues?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 899
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_venues_cited_by_count_range(self, client):
        res = client.get("/venues?filter=cited_by_count:20-21")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 16
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20 or result["cited_by_count"] == 21

    def test_venues_cited_by_count_error(self, client):
        res = client.get("/venues?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestVenuesXConceptsIDFilter:
    count = 4057

    def test_venues_x_concepts_id_short(self, client):
        res = client.get("/venues?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_venues_x_concepts_id_long(self, client):
        res = client.get("/venues?filter=x_concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_venues_x_concepts_id_alias_1(self, client):
        res = client.get("/venues?filter=concept.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_venues_x_concepts_id_alias_2(self, client):
        res = client.get("/venues?filter=concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == self.count
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestVenuesOAFilters:
    def test_venues_is_oa(self, client):
        res = client.get("/venues?filter=is_oa:TRue")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1351
        for result in json_data["results"][:25]:
            assert result["is_oa"] == True

    def test_venues_is_in_doaj(self, client):
        res = client.get("/venues?filter=is_in_doaj:FaLse")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7323
        for result in json_data["results"][:25]:
            assert result["is_in_doaj"] == False


class TestVenuesPublisher:
    def test_venues_publisher_single(self, client):
        res = client.get("/venues?filter=publisher:ElseVier")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1071
        for result in json_data["results"]:
            assert result["publisher"] == "Elsevier"


class TestVenuesExternalIDs:
    def test_venues_has_issn_true(self, client):
        res = client.get("/venues?filter=has_issn:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8823
        for result in json_data["results"][:25]:
            assert result["ids"]["issn"] is not None

    def test_venues_has_issn_false(self, client):
        res = client.get("/venues?filter=has_issn:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1177
        for result in json_data["results"][:25]:
            assert "issn" not in result["ids"] or result["ids"]["issn"] is None

    def test_venues_has_issn_error(self, client):
        res = client.get("/venues?filter=has_issn:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for has_issn must be true or false, not stt."
        )


class TestVenuesMultipleIDs:
    def test_venues_openalex_multiple_long(self, client):
        res = client.get(
            "/venues?filter=openalex_id:https://openalex.org/V41354064|https://openalex.org/V49861241"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/V41354064"
        assert json_data["results"][1]["id"] == "https://openalex.org/V49861241"

    def test_venues_issn_single(self, client):
        res = client.get("/venues?filter=issn:1431-5890")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert "1431-5890" in json_data["results"][0]["issn"]

    def test_concepts_wikidata_multiple(self, client):
        res = client.get("/venues?filter=issn:1431-5890|0140-6736")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert "1431-5890" in json_data["results"][0]["issn"]
        assert "0140-6736" in json_data["results"][1]["issn"]


class TestVenuesType:
    def test_venues_type_single(self, client):
        res = client.get("/venues?filter=type:joUrnal")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9972
        for result in json_data["results"]:
            assert result["type"] == "journal"

    def test_venues_type_not(self, client):
        res = client.get("/venues?filter=type:!journal")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 28
        for result in json_data["results"]:
            assert "type" not in result or result["type"] != "journal"

    def test_venues_type_group_by(self, client):
        res = client.get("/venues?group-by=type")
        json_data = res.get_json()
        assert json_data["group_by"] == [
            {"key": "journal", "key_display_name": "journal", "count": 9972},
            {
                "key": "unknown",
                "key_display_name": "unknown",
                "count": 28,
            },
        ]


class TestVenuesCountryCode:
    def test_venues_country_code_single(self, client):
        res = client.get("/venues?filter=country_code:uS")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2726
        for result in json_data["results"]:
            assert result["country_code"] == "US"

    def test_venues_country_code_not(self, client):
        res = client.get("/venues?filter=country_code:!us")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7274
        for result in json_data["results"]:
            assert "country_code" not in result or result["country_code"] != "US"

    def test_venues_country_code_group_by(self, client):
        res = client.get("/venues?group-by=country_code")
        json_data = res.get_json()
        assert json_data["group_by"][0] == {
            "key": "US",
            "key_display_name": "United States of America",
            "count": 2726,
        }
        assert json_data["group_by"][1] == {
            "key": "GB",
            "key_display_name": "United Kingdom of Great Britain and Northern Ireland",
            "count": 2408,
        }


class TestRelevanceScore:
    def test_relevance_hidden(self, client):
        res = client.get("/venues")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" not in result

    def test_relevance_displayed_filter_search(self, client):
        res = client.get("/venues?filter=display_name.search:nature")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" in result
        assert result["relevance_score"] > 0.0

    def test_relevance_displayed_regular_search(self, client):
        res = client.get("/venues?search=nature")
        json_data = res.get_json()
        result = json_data["results"][0]
        assert "relevance_score" in result


class TestRaiseError:
    def test_error_or_query_between_filters(self, client):
        res = client.get("/venues?filter=has_issn:false|works_count:>100")
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
