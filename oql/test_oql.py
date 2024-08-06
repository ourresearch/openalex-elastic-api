import unittest

import requests

from oql.query import Query

LOCAL_ENDPOINT = "http://127.0.0.1:5000/"

"""
Start local server first. Then run:
python -m unittest discover oql
"""


class TestWorks(unittest.TestCase):
    default_response = "using works\nget works\nsort by display_name asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status"
    default_old_query = "/works?page=1&per_page=25&sort=display_name:asc"

    def test_get_works_simple_query_valid(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), self.default_old_query)
        self.assertEqual(query.oql_query(), self.default_response)
        self.assertTrue(query.is_valid())

    def test_works_filter_publication_year(self):
        query_string = "get works where publication_year is 2020"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/works?page=1&per_page=25&sort=display_name:asc&filter=publication_year:2020"
        )
        self.assertEqual(query.oql_query(), "using works\nget works where publication_year is 2020\nsort by display_name asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

    def test_works_sort_by_publication_year(self):
        query_string = "get works sort by publication_year"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=publication_year:desc")
        self.assertEqual(query.oql_query(), "using works\nget works\nsort by publication_year desc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

    def test_works_return_columns(self):
        query_string = "get works return title, publication_year"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/works?select=title,publication_year&page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget works\nsort by display_name asc\nreturn title, publication_year")
        self.assertTrue(query.is_valid())

    def test_works_using_clause(self):
        query_string = "using works\nget works"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), self.default_old_query)
        self.assertEqual(query.oql_query(), self.default_response)
        self.assertTrue(query.is_valid())

    def test_works_using_clause_with_filter(self):
        query_string = "using works\nget works where publication_year is 2020"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/works?page=1&per_page=25&sort=display_name:asc&filter=publication_year:2020"
        )
        self.assertEqual(query.oql_query(), "using works\nget works where publication_year is 2020\nsort by display_name asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

    def test_works_using_clause_with_sort(self):
        query_string = "using works\nget works\nsort by publication_year asc"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=publication_year:asc")
        self.assertEqual(query.oql_query(), "using works\nget works\nsort by publication_year asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

    def test_works_using_clause_with_sort_and_sort_order(self):
        query_string = "using works\n get works\nsort by display_name desc\n return display_name, publication_year, type"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/works?select=display_name,publication_year,type&page=1&per_page=25&sort=display_name:desc")
        self.assertEqual(query.oql_query(), "using works\nget works\nsort by display_name desc\nreturn display_name, publication_year, type")
        self.assertTrue(query.is_valid())

    def test_works_results_table(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/results?q=get works&format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["results"]["header"][0]["id"], "display_name")
        self.assertEqual(data["results"]["header"][1]["id"], "publication_year")
        work_id = data["results"]["body"][0]["id"]
        self.assertTrue(work_id.startswith("works/"))
        self.assertEqual(data["results"]["body"][0]["cells"][1]["type"], "number")

    def test_works_entity(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/works/W1991071293?format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("props", data)
        self.assertEqual(data["props"][0]["value"], "works/W1991071293")
        self.assertEqual(data["props"][0]["config"]["id"], "id")


class TestAuthors(unittest.TestCase):
    def test_authors_simple_valid(self):
        query_string = "get authors"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/authors?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget authors\nsort by display_name asc\nreturn display_name, display_name_alternatives, last_known_institutions.id, ids.orcid")
        self.assertTrue(query.is_valid())

    def test_authors_sort_by(self):
        query_string = "using works get authors sort by display_name"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/authors?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget authors\nsort by display_name asc\nreturn display_name, display_name_alternatives, last_known_institutions.id, ids.orcid")
        self.assertTrue(query.is_valid())

    def test_authors_get_authors_return_columns(self):
        query_string = "get authors return display_name, ids.orcid"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/authors?select=display_name,ids&page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget authors\nsort by display_name asc\nreturn display_name, ids.orcid")
        self.assertTrue(query.is_valid())

    def test_authors_using_works_get_authors_return_columns(self):
        query_string = "using works\nget authors\nreturn display_name, ids.orcid"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/authors?select=display_name,ids&page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget authors\nsort by display_name asc\nreturn display_name, ids.orcid")
        self.assertTrue(query.is_valid())

    def test_authors_results_table(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/results?q=using works\nget authors&format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["results"]["header"][0]["id"], "display_name")
        author_id = data["results"]["body"][0]["id"]
        self.assertTrue(author_id.startswith("authors/"))
        self.assertEqual(data["results"]["body"][0]["cells"][0]["type"], "string")

    def test_authors_entity(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/authors/A5014517712?format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("props", data)
        self.assertEqual(data["props"][0]["value"], "authors/A5014517712")
        self.assertEqual(data["props"][0]["config"]["id"], "id")


class TestSources(unittest.TestCase):
    def test_sources_simple_valid(self):
        query_string = "using works\nget sources"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/sources?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget sources\nsort by display_name asc\nreturn display_name, ids.issn, type, publisher, is_oa, is_in_doaj")
        self.assertTrue(query.is_valid())

    def test_sources_filter_by_type(self):
        query_string = "get sources where type is journal"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/sources?page=1&per_page=25&sort=display_name:asc&filter=type:journal")
        self.assertEqual(query.oql_query(), "using works\nget sources where type is journal\nsort by display_name asc\nreturn display_name, ids.issn, type, publisher, is_oa, is_in_doaj")
        self.assertTrue(query.is_valid())

    def test_sources_filter_by_repository(self):
        query_string = "using works\nget sources where type is repository"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/sources?page=1&per_page=25&sort=display_name:asc&filter=type:repository")
        self.assertEqual(query.oql_query(), "using works\nget sources where type is repository\nsort by display_name asc\nreturn display_name, ids.issn, type, publisher, is_oa, is_in_doaj")
        self.assertTrue(query.is_valid())

    def test_sources_results_table(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/results?q=using works\nget sources where type is repository&format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["results"]["header"][0]["id"], "display_name")
        source_id = data["results"]["body"][0]["id"]
        self.assertTrue(source_id.startswith("sources/"))
        self.assertEqual(data["results"]["body"][0]["cells"][0]["type"], "string")

    def test_sources_results_table_type_entity(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/results?q=using works\nget sources where type is repository\nreturn type&format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        result = data["results"]["body"][0]["cells"][0]
        self.assertEqual(result["type"], "entity")
        self.assertEqual(result["value"]["id"], "source-types/repository")
        self.assertEqual(result["value"]["display_name"], "repository")

    def test_sources_entity(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/sources/S65028347?format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("props", data)
        self.assertEqual(data["props"][0]["value"], "sources/S65028347")
        self.assertEqual(data["props"][0]["config"]["id"], "id")


class TestInstitutions(unittest.TestCase):
    def test_institutions_valid(self):
        query_string = "get institutions"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/institutions?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget institutions\nsort by display_name asc\nreturn display_name, type, country_code, parent_institutions, child_institutions, ids.ror")
        self.assertTrue(query.is_valid())

    def test_institutions_where_country_is_france(self):
        query_string = "get institutions where country_code is countries/fr"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/institutions?page=1&per_page=25&sort=display_name:asc&filter=country_code:countries/fr")
        self.assertEqual(query.oql_query(), "using works\nget institutions where country_code is countries/fr\nsort by display_name asc\nreturn display_name, type, country_code, parent_institutions, child_institutions, ids.ror")
        self.assertTrue(query.is_valid())

    def test_institutions_using_where_country_is_france(self):
        query_string = "using works\nget institutions where country_code is countries/fr"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/institutions?page=1&per_page=25&sort=display_name:asc&filter=country_code:countries/fr")
        self.assertEqual(query.oql_query(), "using works\nget institutions where country_code is countries/fr\nsort by display_name asc\nreturn display_name, type, country_code, parent_institutions, child_institutions, ids.ror")
        self.assertTrue(query.is_valid())

    def test_instutions_return_columns(self):
        query_string = "using works\nget institutions return display_name, type"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/institutions?select=display_name,type&page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget institutions\nsort by display_name asc\nreturn display_name, type")
        self.assertTrue(query.is_valid())

    def test_institutions_results_table(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/results?q=using works\nget institutions return display_name, type&format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["results"]["header"][0]["id"], "display_name")
        institution_id = data["results"]["body"][0]["id"]
        self.assertTrue(institution_id.startswith("institutions/"))
        self.assertEqual(data["results"]["body"][0]["cells"][0]["type"], "string")

    def test_instutions_entity(self):
        r = requests.get(f"{LOCAL_ENDPOINT}/institutions/I4210158076?format=ui")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("props", data)
        self.assertEqual(data["props"][0]["value"], "institutions/I4210158076")
        self.assertEqual(data["props"][0]["config"]["id"], "id")


class TestPublisher(unittest.TestCase):
    def test_publishers_valid(self):
        query_string = "get publishers"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/publishers?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget publishers\nsort by display_name asc\nreturn display_name")
        self.assertTrue(query.is_valid())


class TestTopics(unittest.TestCase):
    def test_topics_valid(self):
        query_string = "get topics"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/topics?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget topics\nsort by display_name asc\nreturn display_name, description, siblings, subfield, field, domain")
        self.assertTrue(query.is_valid())


class TestInvalidQueries(unittest.TestCase):
    def test_entity_invalid(self):
        query_string = "get invalid"
        query = Query(query_string=query_string)
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_entity_invalid_verb(self):
        query_string = "inva"
        query = Query(query_string=query_string)
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_entity_partial_very_short(self):
        query_string = "g"
        query = Query(query_string=query_string)
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


if __name__ == "__main__":
    unittest.main()
