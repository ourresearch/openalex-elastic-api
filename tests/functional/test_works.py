import pytest


class TestWorksSearch:
    def test_works_search_full(self, client):
        res = client.get("/works?filter=display_name.search:factor%20analysis")
        json_data = res.get_json()
        assert "factor analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "factor analysis" in result["display_name"].lower()

    def test_works_search_alias(self, client):
        res = client.get("/works?filter=title.search:factor%20analysis")
        json_data = res.get_json()
        assert "factor analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "factor analysis" in result["display_name"].lower()

    def test_works_search_phrase(self, client):
        res = client.get('/works?filter=title.search:"factor%20analysis"')
        json_data = res.get_json()
        assert "factor analysis" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "factor analysis" in result["display_name"].lower()

    @pytest.mark.skip
    def test_works_search_exact(self, client):
        """Exact search filter needs to be implemented."""
        res = client.get("/works?filter=display_name:safety")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert result["display_name"].lower() == "safety"


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
            == "Value for param from_publication_date must be a date in format 2020-05-17."
        )

    def test_works_to_publication_date_error(self, client):
        res = client.get("/works?filter=to_publication_date:2020-01-40")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param to_publication_date must be a date in format 2020-05-17."
        )

    def test_works_publication_date_error(self, client):
        res = client.get("/works?filter=publication_date:2020-01-555")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for param publication_date must be a date in format 2020-05-17."
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
            == "Value for is_retracted must be true, false null, or !null: not falsee"
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
        res = client.get("/works?filter=oa_status:gold,oa_status:green")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["open_access"]["oa_status"] == "gold"
                or result["open_access"]["oa_status"] == "green"
            )

    def test_works_oa_status_or_query_with_alias(self, client):
        res = client.get("/works?filter=oa_status:gold,open_access.oa_status:green")
        json_data = res.get_json()
        for result in json_data["results"][:25]:
            assert (
                result["open_access"]["oa_status"] == "gold"
                or result["open_access"]["oa_status"] == "green"
            )

    def test_works_oa_status_multiple_or_queries(self, client):
        res = client.get(
            "/works?filter=publication_year:2020,publication_year:2021,oa_status:gold,oa_status:green&sort=open_access.oa_status"
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
        res = client.get("/works?filter=oa_status:!closed")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7709
        for result in json_data["results"][:50]:
            assert result["open_access"]["oa_status"] != "closed"


class TestWorksMultipleFilter:
    def test_works_multiple(self, client):
        res = client.get(
            "/works?filter=publication-year:2020,publication-year:2021,oa-status:closed"
        )
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
