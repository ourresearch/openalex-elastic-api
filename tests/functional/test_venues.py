class TestVenuesSearch:
    def test_venues_search(self, client):
        res = client.get("/venues?search=university")
        json_data = res.get_json()
        assert "university" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "university" in result["display_name"].lower()

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
        assert json_data["meta"]["count"] == 4
        for result in json_data["results"][:25]:
            assert result["works_count"] == 850

    def test_venues_works_count_greater_than(self, client):
        res = client.get("/venues?filter=works_count:>200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8429
        for result in json_data["results"][:25]:
            assert result["works_count"] > 200

    def test_venues_works_count_less_than(self, client):
        res = client.get("/venues?filter=works_count:<200")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1566
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
        assert json_data["meta"]["count"] == 3
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_venues_cited_by_count_greater_than(self, client):
        res = client.get("/venues?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9776
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_venues_cited_by_count_less_than(self, client):
        res = client.get("/venues?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 221
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_venues_cited_by_count_range(self, client):
        res = client.get("/venues?filter=cited_by_count:20-21")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10
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
    def test_venues_x_concepts_id_short(self, client):
        res = client.get("/venues?filter=x_concepts.id:c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True

    def test_venues_x_concepts_id_long(self, client):
        res = client.get("/venues?filter=x_concepts.id:https://openalex.org/c185592680")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["x_concepts"]:
            if concept["id"] == "https://openalex.org/C185592680":
                concept_found = True
        assert concept_found == True


class TestVenuesOAFilters:
    def test_venues_is_oa(self, client):
        res = client.get("/venues?filter=is_oa:TRue")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1337
        for result in json_data["results"][:25]:
            assert result["is_oa"] == True

    def test_venues_is_in_doaj(self, client):
        res = client.get("/venues?filter=is_in_doaj:FaLse")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7322
        for result in json_data["results"][:25]:
            assert result["is_in_doaj"] == False


class TestVenuesPublisher:
    def test_venues_publisher_single(self, client):
        res = client.get("/venues?filter=publisher:ElseVier")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1074
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
            assert result["ids"]["issn"] is None

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
