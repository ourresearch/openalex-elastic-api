class TestWorksSearch:
    def test_works_search(self, client):
        res = client.get("/works?search=analysis")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 219
        assert "analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "analysis" in result["display_name"].lower()

    def test_works_search_blank(self, client):
        res = client.get('/works?search=""')
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000

    def test_works_search_display_name(self, client):
        res = client.get("/works?filter=display_name.search:analysis")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 219
        assert "analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "analysis" in result["display_name"].lower()

    def test_works_search_alias(self, client):
        res = client.get("/works?filter=title.search:factor%20analysis")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            display_name = result["display_name"].lower()
            assert (
                "factor" in display_name or "factors" in display_name
            ) and "analysis" in display_name

    def test_works_search_phrase(self, client):
        res = client.get('/works?filter=title.search:"factor%20analysis"')
        json_data = res.get_json()
        assert "factor analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "factor analysis" in result["display_name"].lower()

    def test_works_search_exact(self, client):
        res = client.get(
            "/works?filter=display_name:Fusing Location Data for Depression Prediction"
        )
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["display_name"]
                == "Fusing Location Data for Depression Prediction"
            )


class TestWorksPublicationYearFilter:
    def test_works_publication_year_equal(self, client):
        res = client.get("/works?filter=publication_year:2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 27
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893840989"
        assert json_data["results"][0]["cited_by_count"] == 2
        assert res.status_code == 200

    def test_works_publication_year_greater_than(self, client):
        res = client.get("/works?filter=publication_year:>2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_year_less_than(self, client):
        res = client.get("/works?filter=publication_year:<2020")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9966
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893871524"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_year_error(self, client):
        res = client.get("/works?filter=publication_year:ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param publication_year must be a number."
        )


class TestWorksPublicationDateFilter:
    def test_works_publication_date_equal(self, client):
        res = client.get("/works?filter=publication_date:2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893038645"
        assert json_data["results"][0]["cited_by_count"] == 1
        assert res.status_code == 200

    def test_works_publication_date_greater_than(self, client):
        res = client.get("/works?filter=publication_date:>2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 30
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_publication_date_less_than(self, client):
        res = client.get("/works?filter=publication_date:<2020-01-01")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9966
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893871524"
        assert json_data["results"][0]["cited_by_count"] == 0
        assert res.status_code == 200

    def test_works_from_to_publication_date(self, client):
        res = client.get(
            "/works?filter=from_publication_date:2020-01-01,to_publication_date:2020-01-02"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] > 0
        for result in json_data["results"][:25]:
            assert (
                result["publication_date"] == "2020-01-01"
                or result["publication_date"] == "2020-01-02"
            )

    def test_works_from_publication_date_error(self, client):
        res = client.get("/works?filter=from_publication_date:2020-01-40")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param from_publication_date is an invalid date. Format is yyyy-mm-dd (e.g. 2020-05-17)."
        )

    def test_works_to_publication_date_error(self, client):
        res = client.get("/works?filter=to_publication_date:2020-01-40")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param to_publication_date is an invalid date. Format is yyyy-mm-dd (e.g. 2020-05-17)."
        )

    def test_works_publication_date_error(self, client):
        res = client.get("/works?filter=publication_date:2020-1-17")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param publication_date is an invalid date. Format is yyyy-mm-dd (e.g. 2020-05-17)."
        )


class TestWorksHostVenueFilters:
    def test_works_host_venue_issn(self, client):
        res = client.get("/works?filter=host_venue.issn:2332-7790")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"]:
            assert "2332-7790" in result["host_venue"]["issn"]

    def test_works_host_venue_publisher_single(self, client):
        res = client.get("/works?filter=host_venue.publisher:ElseVier Bv")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 36
        for result in json_data["results"]:
            assert result["host_venue"]["publisher"] == "Elsevier BV"

    def test_works_host_venue_id_short(self, client):
        res = client.get("/works?filter=host_venue.id:v2898264183")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["publication_date"] == "2019-09-01"
        assert (
            json_data["results"][0]["host_venue"]["display_name"]
            == "Health Professions Education"
        )
        assert json_data["results"][0]["host_venue"]["publisher"] == "Elsevier BV"
        assert res.status_code == 200

    def test_works_host_venue_id_long(self, client):
        res = client.get("/works?filter=host_venue.id:https://openalex.org/v2898264183")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["publication_date"] == "2019-09-01"
        assert (
            json_data["results"][0]["host_venue"]["display_name"]
            == "Health Professions Education"
        )
        assert json_data["results"][0]["host_venue"]["publisher"] == "Elsevier BV"
        assert res.status_code == 200


class TestWorksTypeFilter:
    def test_works_type(self, client):
        res = client.get("/works?filter=type:journAl-arTicle")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2884
        for result in json_data["results"][:25]:
            assert result["type"] == "journal-article"


class TestWorksBooleanFilters:
    def test_works_is_paratext(self, client):
        res = client.get("/works?filter=is_paratext:False")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3332
        for result in json_data["results"][:25]:
            assert result["is_paratext"] == False

    def test_works_is_oa(self, client):
        res = client.get("/works?filter=is_oa:tRue")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7709
        for result in json_data["results"][:25]:
            assert result["open_access"]["is_oa"] == True

    def test_works_is_retracted(self, client):
        res = client.get("/works?filter=is_retracted:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 10000
        for result in json_data["results"][:25]:
            assert result["is_retracted"] == False

    def test_works_boolean_error(self, client):
        res = client.get("/works?filter=is_retracted:falsee")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for is_retracted must be true, false null, or !null: not falsee."
        )


class TestWorksAuthorFilters:
    author_name = "Leonardo Ferreira Almada"

    def test_works_author_id_short(self, client):
        res = client.get("/works?filter=author.id:A2698836828")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["author"]["display_name"]
            == self.author_name
        )

    def test_works_author_id_long(self, client):
        res = client.get("/works?filter=author.id:https://openalex.org/a2698836828")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["author"]["display_name"]
            == self.author_name
        )

    def test_works_author_orcid(self, client):
        res = client.get(
            "/works?filter=author.orcid:https://orcid.org/0000-0002-9777-5667"
        )
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["author"]["display_name"]
            == self.author_name
        )


class TestWorksInstitutionsFilters:
    institution_name = "University of Connecticut"

    def test_works_institutions_id_short(self, client):
        res = client.get("/works?filter=institutions.id:I140172145")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["institutions"][0]["display_name"]
            == self.institution_name
        )

    def test_works_institutions_id_long(self, client):
        res = client.get(
            "/works?filter=institutions.id:https://openalex.org/I140172145"
        )
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["institutions"][0]["display_name"]
            == self.institution_name
        )

    def test_works_institutions_ror(self, client):
        res = client.get("/works?filter=institutions.ror:https://ror.org/02der9h97")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["authorships"][0]["institutions"][0]["display_name"]
            == self.institution_name
        )

    def test_works_institutions_country_code(self, client):
        res = client.get("/works?filter=institutions.country_code:de")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 198
        assert (
            json_data["results"][0]["authorships"][0]["institutions"][0]["country_code"]
            == "DE"
        )

    def test_works_institutions_type(self, client):
        res = client.get("/works?filter=institutions.type:Education")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2030
        assert (
            json_data["results"][0]["authorships"][0]["institutions"][0]["type"]
            == "education"
        )


class TestWorksCitedByCountFilter:
    def test_works_cited_by_count_equal(self, client):
        res = client.get("/works?filter=cited_by_count:20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 25
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20

    def test_works_cited_by_count_greater_than(self, client):
        res = client.get("/works?filter=cited_by_count:>20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 432
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] > 20

    def test_works_cited_by_count_less_than(self, client):
        res = client.get("/works?filter=cited_by_count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9543
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_works_cited_by_count_less_than_hyphen(self, client):
        res = client.get("/works?filter=cited-by-count:<20")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9543
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] < 20

    def test_works_cited_by_count_range(self, client):
        res = client.get("/works?filter=cited-by-count:20-21")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 51
        for result in json_data["results"][:25]:
            assert result["cited_by_count"] == 20 or result["cited_by_count"] == 21

    def test_works_cited_by_count_range_error(self, client):
        res = client.get("/works?filter=cited-by-count:20-ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )

    def test_works_range_error(self, client):
        res = client.get("/works?filter=cited_by_count:>ff")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for param cited_by_count must be a number."
        )


class TestWorksConcepts:
    concept_name = "Computer science"

    def test_works_concepts_id_short(self, client):
        res = client.get("/works?filter=concepts.id:c41008148")
        json_data = res.get_json()
        concept_found = False
        for concept in json_data["results"][0]["concepts"]:
            if concept["display_name"] == self.concept_name:
                concept_found = True
        assert concept_found == True

    def test_works_concepts_id_long(self, client):
        res = client.get("/works?filter=concepts.id:https://openalex.org/C41008148")
        concept_found = False
        json_data = res.get_json()
        for concept in json_data["results"][0]["concepts"]:
            if concept["display_name"] == self.concept_name:
                concept_found = True
        assert concept_found == True


class TestWorksAlternateHostVenues:
    def test_works_alternate_host_venues_id_short(self, client):
        """Needs to be made case insensitive."""
        res = client.get("/works?filter=alternate_host_venues.id:V173526857")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["alternate_host_venues"][0]["id"]
                == "https://openalex.org/V173526857"
            )

    def test_works_alternate_host_venues_id_long(self, client):
        """Needs to be made case insensitive."""
        res = client.get(
            "/works?filter=alternate_host_venues.id:https://openalex.org/V173526857"
        )
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["alternate_host_venues"][0]["id"]
                == "https://openalex.org/V173526857"
            )

    def test_works_alternate_host_venues_license(self, client):
        res = client.get("/works?filter=alternate_host_venues.license:CC-by-nc")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["alternate_host_venues"][0]["license"] == "cc-by-nc"
        )

    def test_works_alternate_host_venues_version(self, client):
        res = client.get("/works?filter=alternate_host_venues.version:publishedversion")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["alternate_host_venues"][0]["version"]
            == "publishedVersion"
        )


class TestWorksReferencedWorks:
    def test_works_referenced_works_short(self, client):
        res = client.get("/works?filter=referenced_works:W2516086211")
        json_data = res.get_json()
        assert (
            "https://openalex.org/W2516086211"
            in json_data["results"][0]["referenced_works"]
        )

    def test_works_referenced_works_long(self, client):
        res = client.get(
            "/works?filter=referenced_works:https://openalex.org/W2516086211"
        )
        json_data = res.get_json()
        assert (
            "https://openalex.org/W2516086211"
            in json_data["results"][0]["referenced_works"]
        )

    def test_works_cites_short(self, client):
        res = client.get("/works?filter=cites:W2516086211")
        json_data = res.get_json()
        assert (
            "https://openalex.org/W2516086211"
            in json_data["results"][0]["referenced_works"]
        )

    def test_works_cites_long(self, client):
        res = client.get("/works?filter=cites:https://openalex.org/W2516086211")
        json_data = res.get_json()
        assert (
            "https://openalex.org/W2516086211"
            in json_data["results"][0]["referenced_works"]
        )


class TestWorksOAStatus:
    def test_works_oa_status(self, client):
        res = client.get("/works?filter=oa_status:Closed")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["open_access"]["oa_status"] == "closed"

    def test_works_oa_status_or_query(self, client):
        res = client.get("/works?filter=oa_status:gold|green")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["open_access"]["oa_status"] == "gold"
                or result["open_access"]["oa_status"] == "green"
            )

    def test_works_oa_status_multiple_or_queries(self, client):
        res = client.get(
            "/works?filter=publication_year:2020|2021,oa_status:gold|green&sort=open_access.oa_status"
        )
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["open_access"]["oa_status"] == "gold"
                or result["open_access"]["oa_status"] == "green"
            )

    def test_works_oa_status_hyphen_filter(self, client):
        res = client.get("/works?filter=oa-status:Closed")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["open_access"]["oa_status"] == "closed"

    def test_works_oa_status_alias(self, client):
        res = client.get("/works?filter=open_access.oa_status:open")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["open_access"]["oa_status"] == "open"


class TestWorksNullNotNull:
    def test_works_oa_status_null(self, client):
        res = client.get("/works?filter=oa_status:null")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["open_access"]["oa_status"] == None

    def test_works_oa_status_not_null(self, client):
        res = client.get("/works?filter=oa_status:!null")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["open_access"]["oa_status"] != None


class TestWorksNotFilter:
    def test_works_oa_status_not_term(self, client):
        """Tests ! filter for term field."""
        res = client.get("/works?filter=oa_status:!closed")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7709
        for result in json_data["results"][:50]:
            assert result["open_access"]["oa_status"] != "closed"

    def test_works_concepts_not_term_short(self, client):
        """Tests ! filter for OpenAlexID field (short version)."""
        res_1 = client.get("/works?filter=concepts.id:!c41008148")
        json_data_1 = res_1.get_json()
        for result in json_data_1["results"][:50]:
            for concept in result["concepts"]:
                assert concept["id"] != "https://openalex.org/C41008148"

        res_2 = client.get("/works?filter=concepts.id:c41008148")
        json_data_2 = res_2.get_json()
        assert json_data_1["meta"]["count"] + json_data_2["meta"]["count"] == 10000

    def test_works_concepts_not_term_full(self, client):
        """Tests ! filter for OpenAlexID field (long version)."""
        res_1 = client.get("/works?filter=concepts.id:!https://openalex.org/C41008148")
        json_data_1 = res_1.get_json()
        for result in json_data_1["results"][:50]:
            for concept in result["concepts"]:
                assert concept["id"] != "https://openalex.org/C41008148"

        res_2 = client.get("/works?filter=concepts.id:c41008148")
        json_data_2 = res_2.get_json()
        assert json_data_1["meta"]["count"] + json_data_2["meta"]["count"] == 10000

    def test_works_publisher_not_term(self, client):
        """Tests ! filter for phrase field."""
        res_1 = client.get("/works?filter=host_venue.publisher:!elsevier")
        json_data_1 = res_1.get_json()
        for result in json_data_1["results"][:50]:
            assert result["host_venue"]["publisher"] != "elsevier"

        res_2 = client.get("/works?filter=host_venue.publisher:elsevier")
        json_data_2 = res_2.get_json()
        assert json_data_1["meta"]["count"] + json_data_2["meta"]["count"] == 10000


class TestWorksMultipleFilter:
    def test_works_multiple(self, client):
        res = client.get("/works?filter=publication-year:2020|2021,oa-status:closed")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 13
        for result in json_data["results"][:25]:
            assert (
                result["publication_year"] == 2020 or result["publication_year"] == 2021
            )
            assert result["open_access"]["oa_status"] == "closed"


class TestWorksInvalidFields:
    def test_works_invalid_publication_year(self, client):
        res = client.get("/works?filter=publication-yearrr:2020")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"].startswith(
            "publication_yearrr is not a valid field. Valid fields are underscore or hyphenated versions of:"
        )


class TestWorksAuthorOrQuery:
    def test_works_author_and_query(self, client):
        res = client.get("/works?filter=author.id:a2698836828,author.id:A2761130472")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["authorships"][0]["author"]["id"]
            == "https://openalex.org/A2698836828"
        )
        assert (
            json_data["results"][0]["authorships"][1]["author"]["id"]
            == "https://openalex.org/A2761130472"
        )

    def test_works_author_or_query(self, client):
        res = client.get(
            "/works?filter=author.id:https://openalex.org/a2698836828|A2565156079|A277790681"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3
        for result in json_data["results"]:
            found = False
            for author in result["authorships"]:
                if (
                    author["author"]["id"] == "https://openalex.org/A2698836828"
                    or author["author"]["id"] == "https://openalex.org/A2565156079"
                    or author["author"]["id"] == "https://openalex.org/A277790681"
                ):
                    found = True
            assert found is True

    def test_works_author_or_query_with_and(self, client):
        """The and query takes precedence, so 1 result is returned."""
        res = client.get(
            "/works?filter=author.id:https://openalex.org/a2698836828|A2565156079|A277790681,author.id:A2761130472"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1

    def test_works_author_or_query_negate_all(self, client):
        """Numbers together should equal 10,000."""

        # in the dataset
        res1 = client.get("/works?filter=author.id:a2698836828|A2565156079")
        json_data1 = res1.get_json()
        assert json_data1["meta"]["count"] == 2

        # not in the dataset
        res2 = client.get("/works?filter=author.id:!a2698836828|A2565156079")
        json_data2 = res2.get_json()
        assert json_data2["meta"]["count"] == 9998

    def test_works_author_or_query_not_error(self, client):
        res = client.get("/works?filter=author.id:A2565156079|!A277790681")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"].startswith(
            "The ! operator can only be used at the beginning of an OR query, "
            "like /works?filter=concepts.id:!C144133560|C15744967, meaning NOT (C144133560 or C15744967). Problem "
            "value: !A277790681"
        )


class TestWorksExternalIDs:
    def test_works_has_doi_true(self, client):
        res = client.get("/works?filter=has_doi:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3627
        for result in json_data["results"][:25]:
            assert result["ids"]["doi"] is not None

    def test_works_has_doi_false(self, client):
        res = client.get("/works?filter=has_doi:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6373
        for result in json_data["results"][:25]:
            assert result["ids"]["doi"] is None

    def test_venues_has_doi_error(self, client):
        res = client.get("/works?filter=has_doi:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for has_doi must be true or false, not stt."
        )


class TestWorksMultipleIDs:
    def test_works_openalex_single_long(self, client):
        res = client.get("/works?filter=openalex_id:https://openalex.org/W2893359707")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"

    def test_works_openalex_multiple_long(self, client):
        res = client.get(
            "/works?filter=openalex_id:https://openalex.org/W2893359707|https://openalex.org/W2893173145"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][1]["id"] == "https://openalex.org/W2893173145"

    def test_works_openalex_single_short(self, client):
        res = client.get("/works?filter=openalex_id:w2893359707")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"

    def test_works_openalex_multiple_short(self, client):
        res = client.get("/works?filter=openalex_id:W2893359707|W2893173145")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["id"] == "https://openalex.org/W2893359707"
        assert json_data["results"][1]["id"] == "https://openalex.org/W2893173145"

    def test_works_doi_single_long(self, client):
        res = client.get("/works?filter=doi:https://doi.org/10.23845/kgt.v14i3.277")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["doi"] == "https://doi.org/10.23845/kgt.v14i3.277"
        )

    def test_works_doi_single_short(self, client):
        res = client.get("/works?filter=doi:10.23845/kgt.v14i3.277")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["doi"] == "https://doi.org/10.23845/kgt.v14i3.277"
        )

    def test_works_doi_multiple(self, client):
        res = client.get(
            "/works?filter=doi:https://doi.org/10.23845/kgt.v14i3.277|https://doi.org/10.1109/tbdata.2018.2872569"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert (
            json_data["results"][0]["doi"] == "https://doi.org/10.23845/kgt.v14i3.277"
        )
        assert (
            json_data["results"][1]["doi"]
            == "https://doi.org/10.1109/tbdata.2018.2872569"
        )

    def test_works_mag_single(self, client):
        res = client.get("/works?filter=mag:116536")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["ids"]["mag"] == "116536"

    def test_works_mag_multiple(self, client):
        res = client.get("/works?filter=mag:116536|71948")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["ids"]["mag"] == "116536"
        assert json_data["results"][1]["ids"]["mag"] == "71948"

    def test_works_mag_multiple_alias(self, client):
        res = client.get("/works?filter=ids.mag:116536|71948")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert json_data["results"][0]["ids"]["mag"] == "116536"
        assert json_data["results"][1]["ids"]["mag"] == "71948"

    def test_works_pmid_single_short(self, client):
        res = client.get("/works?filter=pmid:14419794")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/14419794"
        )

    def test_works_pmid_multiple_short(self, client):
        res = client.get("/works?filter=pmid:14419794|13729179")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert (
            json_data["results"][0]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/13729179"
        )
        assert (
            json_data["results"][1]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/14419794"
        )

    def test_works_pmid_multiple_short_alias(self, client):
        res = client.get("/works?filter=ids.pmid:14419794|13729179")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert (
            json_data["results"][0]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/13729179"
        )
        assert (
            json_data["results"][1]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/14419794"
        )

    def test_works_pmid_multiple_long(self, client):
        res = client.get(
            "/works?filter=pmid:https://pubmed.ncbi.nlm.nih.gov/14419794|https://pubmed.ncbi.nlm.nih.gov/13729179"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2
        assert (
            json_data["results"][0]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/13729179"
        )
        assert (
            json_data["results"][1]["ids"]["pmid"]
            == "https://pubmed.ncbi.nlm.nih.gov/14419794"
        )

    def test_works_pmcid_single_short(self, client):
        res = client.get("/works?filter=pmcid:1561523")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["ids"]["pmcid"]
            == "https://www.ncbi.nlm.nih.gov/pmc/articles/1561523"
        )

    def test_works_pmcid_single_short_alias(self, client):
        res = client.get("/works?filter=ids.pmcid:1561523")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["ids"]["pmcid"]
            == "https://www.ncbi.nlm.nih.gov/pmc/articles/1561523"
        )


class TestWorksUniqueOAFilters:
    def test_works_has_oa_accepted_or_published_version_true(self, client):
        res = client.get("/works?filter=has_oa_accepted_or_published_version:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 656

    def test_works_has_oa_accepted_or_published_version_false(self, client):
        res = client.get("/works?filter=has_oa_accepted_or_published_version:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9344

    def test_works_has_oa_submitted_version_true(self, client):
        res = client.get("/works?filter=has_oa_submitted_version:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 179

    def test_works_has_oa_submitted_version_false(self, client):
        res = client.get("/works?filter=has_oa_submitted_version:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9821
