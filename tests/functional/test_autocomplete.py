class TestFullAutoComplete:
    def test_full_autocomplete(self, client):
        res = client.get("/autocomplete?q=sci")
        json_data = res.get_json()
        first_object = json_data["results"][0]
        assert first_object["id"] == "https://openalex.org/P4310320990"
        assert first_object["display_name"] == "Elsevier BV"
        assert first_object["cited_by_count"] == 395389023
        assert first_object["entity_type"] == "publisher"
        assert first_object["external_id"] == "https://www.wikidata.org/entity/Q746413"

    def test_autocomplete_full_sources_additional_fields(self, client):
        res = client.get("/autocomplete?q=jacs")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["display_name"]
            == "Journal of the American Chemical Society"
        )


class TestEntitiesAutoComplete:
    def test_authors_autocomplete(self, client):
        res = client.get("/autocomplete/authors?q=jas")
        json_data = res.get_json()
        assert "jas" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "jas" in result["display_name"].lower()

    def test_concepts_autocomplete(self, client):
        res = client.get("/autocomplete/concepts?q=sci")
        json_data = res.get_json()
        assert "sci" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "sci" in result["display_name"].lower()

    def test_institutions_autocomplete(self, client):
        res = client.get("/autocomplete/institutions?q=uni")
        json_data = res.get_json()
        assert "uni" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "uni" in result["display_name"].lower()

    def test_publishers_autocomplete(self, client):
        res = client.get("/autocomplete/publishers?q=else")
        json_data = res.get_json()
        assert "else" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "else" in result["display_name"].lower()

    def test_sources_autocomplete(self, client):
        res = client.get("/autocomplete/sources?q=nat")
        json_data = res.get_json()
        assert "nat" in json_data["results"][0]["display_name"].lower()
        for result in json_data["results"][:25]:
            assert "nat" in result["display_name"].lower()

    def test_sources_autocomplete_additional_fields(self, client):
        """Search across display_name, alternate_titles, and abbreviated_title."""
        res = client.get("/autocomplete/sources?q=jacs")
        json_data = res.get_json()
        assert (
            json_data["results"][0]["display_name"]
            == "Journal of the American Chemical Society"
        )

    def test_works_autocomplete(self, client):
        res = client.get("/autocomplete/works?q=list")
        json_data = res.get_json()
        first_object = json_data["results"][0]
        assert first_object["id"] == "https://openalex.org/W49131"
        assert (
            first_object["display_name"]
            == "Comparison of Four Commercial DNA Extraction Kits for PCR Detection of Listeria monocytogenes, Salmonella, Escherichia coli O157:H7, and Staphylococcus aureus in Fresh, Minimally Processed Vegetables"
        )
        assert first_object["cited_by_count"] == 31
        assert first_object["entity_type"] == "work"
        assert (
            first_object["external_id"]
            == "https://doi.org/10.4315/0362-028x-71.10.2110"
        )

        for result in json_data["results"][:25]:
            assert "list" in result["display_name"].lower()


class TestCustomAutocomplete:
    def test_institutions_type_autocomplete(self, client):
        res = client.get("/autocomplete/institutions/type?q=co")
        json_data = res.get_json()
        assert json_data["results"][0]["display_name"] == "company"
        assert json_data["results"][0]["cited_by_count"] == 36270237


class TestFiltersInAutocomplete:
    def test_authors_filters_autocomplete(self, client):
        res = client.get(
            "/autocomplete/authors?filter=last_known_institution.country_code:be&q=pet"
        )
        json_data = res.get_json()
        assert "peter vandenabeele" in json_data["results"][0]["display_name"].lower()

    def test_concepts_filters_autocomplete(self, client):
        res = client.get("/autocomplete/concepts?filter=level:3&q=ele")
        json_data = res.get_json()
        assert "electrochemistry" in json_data["results"][0]["display_name"].lower()

    def test_institutions_filters_autocomplete(self, client):
        res = client.get("/autocomplete/institutions?filter=country_code:ge&q=sho")
        json_data = res.get_json()
        assert "shota rustaveli" in json_data["results"][0]["display_name"].lower()

    def test_works_filters_autocomplete(self, client):
        res = client.get(
            "/autocomplete/works?filter=is_oa:true,publication_year:2019&q=tra"
        )
        json_data = res.get_json()
        assert (
            "impacts of automated vehicles"
            in json_data["results"][0]["display_name"].lower()
        )

    def test_works_filters_autocomplete_error(self, client):
        res = client.get(
            "/autocomplete/works?filter=is_oaa:true,publication_year:2019&q=tra"
        )
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert "is_oaa is not a valid field" in json_data["message"]

    def test_full_autocomplete_filter_error(self, client):
        res = client.get("/autocomplete?filter=is_oaa:true,publication_year:2019&q=tra")
        json_data = res.get_json()
        assert res.status_code == 403
        assert json_data["error"] == "Invalid query parameters error."
        assert (
            "filter is not a valid parameter for the full autocomplete endpoint"
            in json_data["message"]
        )


class TestAutocompleteIdDetection:
    def test_author_openalex_id(self, client):
        res = client.get("/autocomplete/authors?q=a2609699")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert "peter vandenabeele" in json_data["results"][0]["display_name"].lower()

    def test_author_orcid(self, client):
        res = client.get(
            "/autocomplete/authors?q=https://orcid.org/0000-0001-5285-9835"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert "peter vandenabeele" in json_data["results"][0]["display_name"].lower()

    def test_author_orcid_urn(self, client):
        res = client.get("/autocomplete/authors?q=orcid:0000-0001-5285-9835")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert "peter vandenabeele" in json_data["results"][0]["display_name"].lower()

    def test_concepts_openalex(self, client):
        res = client.get("/autocomplete/concepts?q=C86803240")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Biology"

    def test_concepts_wikidata(self, client):
        res = client.get("/autocomplete/concepts?q=https://www.wikidata.org/wiki/Q420")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Biology"

    def test_concepts_wikidata_urn(self, client):
        res = client.get("/autocomplete/concepts?q=wikidata:Q420")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Biology"

    def test_institutions_openalex(self, client):
        res = client.get("/autocomplete/institutions?q=https://openalex.org/I19820366")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Chinese Academy of Sciences"

    def test_institutions_ror(self, client):
        res = client.get("/autocomplete/institutions?q=https://ror.org/034t30j35")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Chinese Academy of Sciences"

    def test_institutions_ror_urn(self, client):
        res = client.get("/autocomplete/institutions?q=ror:034t30j35")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Chinese Academy of Sciences"

    def test_works_openalex(self, client):
        res = client.get("/autocomplete/works?q=W37005")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Parkinson's Disease"

    def test_works_doi(self, client):
        res = client.get(
            "/autocomplete/works?q=https://doi.org/10.1056/nejm199810083391506"
        )
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Parkinson's Disease"

    def test_works_doi_urn(self, client):
        res = client.get("/autocomplete/works?q=doi:10.1056/nejm199810083391506")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Parkinson's Disease"

    def test_full_autocomplete_wikidata(self, client):
        res = client.get("/autocomplete?q=https://www.wikidata.org/wiki/Q420")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Biology"

    def test_full_autocomplete_ror(self, client):
        res = client.get("/autocomplete?q=https://ror.org/034t30j35")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Chinese Academy of Sciences"

    def test_full_autocomplete_issn_urn(self, client):
        res = client.get("/autocomplete?q=issn:0002-7863")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert (
            json_data["results"][0]["display_name"]
            == "Journal of the American Chemical Society"
        )

    def test_full_autocomplete_openalex(self, client):
        res = client.get("/autocomplete?q=W37005")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Parkinson's Disease"

    def test_full_autocomplete_doi(self, client):
        res = client.get("/autocomplete?q=https://doi.org/10.1056/nejm199810083391506")
        json_data = res.get_json()
        assert json_data["meta"]["count"] == 1
        assert json_data["results"][0]["display_name"] == "Parkinson's Disease"
