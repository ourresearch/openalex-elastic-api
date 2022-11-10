class TestWorksHasFilters:
    def test_works_has_references(self, client):
        res = client.get("/works?filter=has_references:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2770

    def test_works_has_references_error(self, client):
        res = client.get("/works?filter=has_references:null")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"]
            == "Value for has_references must be true or false, not null."
        )


class TestWorksUniqueOAFilters:
    def test_works_has_oa_accepted_or_published_version_true(self, client):
        res = client.get("/works?filter=has_oa_accepted_or_published_version:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 924

    def test_works_has_oa_accepted_or_published_version_false(self, client):
        res = client.get("/works?filter=has_oa_accepted_or_published_version:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9076

    def test_works_has_oa_submitted_version_true(self, client):
        res = client.get("/works?filter=has_oa_submitted_version:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 354

    def test_works_has_oa_submitted_version_false(self, client):
        res = client.get("/works?filter=has_oa_submitted_version:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9646


class TestWorksExternalIDs:
    def test_works_has_doi_true(self, client):
        res = client.get("/works?filter=has_doi:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 3718
        for result in json_data["results"][:25]:
            assert result["ids"]["doi"] is not None

    def test_works_has_doi_false(self, client):
        res = client.get("/works?filter=has_doi:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 6282
        for result in json_data["results"][:25]:
            assert "doi" not in result["ids"] or result["ids"]["doi"] is None

    def test_venues_has_doi_error(self, client):
        res = client.get("/works?filter=has_doi:stt")
        json_data = res.get_json()
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            json_data["message"] == "Value for has_doi must be true or false, not stt."
        )

    def test_works_has_pmid_true(self, client):
        res = client.get("/works?filter=has_pmid:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 998
        for result in json_data["results"][:25]:
            assert result["ids"]["pmid"] is not None

    def test_works_has_pmid_false(self, client):
        res = client.get("/works?filter=has_pmid:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9002
        for result in json_data["results"][:25]:
            assert "pmid" not in result["ids"]

    def test_works_has_pmcid_true(self, client):
        res = client.get("/works?filter=has_pmcid:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 247
        for result in json_data["results"][:25]:
            assert result["ids"]["pmcid"] is not None

    def test_works_has_pmcid_false(self, client):
        res = client.get("/works?filter=has_pmcid:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9753
        for result in json_data["results"][:25]:
            assert "pmcid" not in result["ids"]


class TestWorksVersionFilters:
    def test_works_version_accepted_version(self, client):
        res = client.get("/works?filter=version:acceptedversion")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 61
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] == "acceptedVersion"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] == "acceptedVersion":
                    found = True
            assert found is True

    def test_works_version_submitted_version(self, client):
        res = client.get("/works?filter=version:submittedversion")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 354
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] == "submittedVersion"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] == "submittedVersion":
                    found = True
            assert found is True

    def test_works_version_published_version(self, client):
        res = client.get("/works?filter=version:publishedversion")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 881
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] == "publishedVersion"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] == "publishedVersion":
                    found = True
            assert found is True

    def test_works_version_null(self, client):
        res = client.get("/works?filter=version:null")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8910
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] is not None
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] is not None:
                    found = True
            assert found is False

    def test_works_version_not_null(self, client):
        res = client.get("/works?filter=version:!null")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1090
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] is not None
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] is not None:
                    found = True
            assert found is True

    def test_works_version_not_published_version(self, client):
        res = client.get("/works?filter=version:!publishedversion")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9119
        for result in json_data["results"]:
            found = False
            if (
                "version" in result["host_venue"]
                and result["host_venue"]["version"] == "publishedVersion"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "version" in venue and venue["version"] == "publishedVersion":
                    found = True
            assert found is False


class TestWorksRepositoryFilter:
    def test_works_repository_short(self, client):
        res = client.get("/works?filter=repository:V28996644")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"]:
            found = False
            if (
                "id" in result["host_venue"]
                and result["host_venue"]["id"] == "https://openalex.org/V28996644"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "id" in venue and venue["id"] == "https://openalex.org/V28996644":
                    found = True
            assert found is True

    def test_works_repository_long(self, client):
        res = client.get("/works?filter=repository:https://openalex.org/V28996644")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        for result in json_data["results"]:
            found = False
            if (
                "id" in result["host_venue"]
                and result["host_venue"]["id"] == "https://openalex.org/V28996644"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "id" in venue and venue["id"] == "https://openalex.org/V28996644":
                    found = True
            assert found is True

    def test_works_repository_not(self, client):
        res = client.get("/works?filter=repository:!https://openalex.org/V28996644")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 9999
        for result in json_data["results"]:
            found = False
            if (
                "id" in result["host_venue"]
                and result["host_venue"]["id"] == "https://openalex.org/V28996644"
            ):
                found = True
            for venue in result["alternate_host_venues"]:
                if "id" in venue and venue["id"] == "https://openalex.org/V28996644":
                    found = True
            assert found is False

    def test_works_repository_null(self, client):
        res = client.get("/works?filter=repository:null")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "'null' is not a valid OpenAlex ID."

    def test_works_repository_not_null(self, client):
        res = client.get("/works?filter=repository:!null")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "'!null' is not a valid OpenAlex ID."

    def test_works_repository_group_by(self, client):
        res = client.get("/works?group_by=repository")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert json_data["message"] == "Cannot group by repository."

    def test_works_repository_filters_view(self, client):
        res = client.get("/works/filters/repository:V28996644")
        json_data = res.get_json()
        assert json_data["filters"][0]["key"] == "repository"
        assert json_data["filters"][0]["is_negated"] == False
        assert json_data["filters"][0]["type"] == "OpenAlexIDField"
        assert json_data["filters"][0]["values"][0]["value"] == "V28996644"
        assert json_data["filters"][0]["values"][0]["count"] == 1
        assert (
            json_data["filters"][0]["values"][0]["display_name"]
            == "Geographie Physique Et Quaternaire"
        )


class TestWorksAuthorsCount:
    def test_works_authors_count_exact(self, client):
        res = client.get("/works?filter=authors_count:1")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 5174
        for result in json_data["results"]:
            assert len(result["authorships"]) == 1

    def test_works_authors_count_lt(self, client):
        res = client.get("/works?filter=authors_count:<5")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8763
        for result in json_data["results"]:
            assert len(result["authorships"]) < 5

    def test_works_authors_count_null(self, client):
        res = client.get("/works?filter=authors_count:null")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8

    def test_works_authors_count_group_by(self, client):
        res = client.get("/works?group_by=authors_count")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "1"
        assert result1["key_display_name"] == "1"
        assert result1["count"] == 5174
        assert result2["key"] == "2"
        assert result2["key_display_name"] == "2"
        assert result2["count"] == 1763


class TestWorksConceptsCount:
    def test_works_concepts_count_exact(self, client):
        res = client.get("/works?filter=concepts_count:1")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1930
        for result in json_data["results"]:
            assert len(result["concepts"]) == 1

    def test_works_concepts_count_lt(self, client):
        res = client.get("/works?filter=concepts_count:<5")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 4294
        for result in json_data["results"]:
            assert len(result["concepts"]) < 5

    def test_works_concepts_count_null(self, client):
        res = client.get("/works?filter=concepts_count:null")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 8

    def test_works_concepts_count_group_by(self, client):
        res = client.get("/works?group_by=concepts_count")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "1"
        assert result1["key_display_name"] == "1"
        assert result1["count"] == 1930
        assert result2["key"] == "3"
        assert result2["key_display_name"] == "3"
        assert result2["count"] == 918


class TestHasOrcid:
    def test_has_orcid_true(self, client):
        res = client.get("/works?filter=has_orcid:true")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 2229
        for result in json_data["results"]:
            found = False
            for authorship in result["authorships"]:
                if "orcid" in authorship["author"] and authorship["author"]["orcid"]:
                    found = True
            assert found is True

    def test_has_orcid_false(self, client):
        res = client.get("/works?filter=has_orcid:false")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 7771
        for result in json_data["results"]:
            found = False
            for authorship in result["authorships"]:
                if "orcid" in authorship["author"] and authorship["author"]["orcid"]:
                    found = True
            assert found is False

    def test_has_orcid_group_by(self, client):
        res = client.get("/works?group_by=has_orcid")
        json_data = res.get_json()
        result1 = json_data["group_by"][0]
        result2 = json_data["group_by"][1]
        assert result1["key"] == "true"
        assert result1["key_display_name"] == "true"
        assert result1["count"] == 2229
        assert result2["key"] == "false"
        assert result2["key_display_name"] == "false"
        assert result2["count"] == 7771
