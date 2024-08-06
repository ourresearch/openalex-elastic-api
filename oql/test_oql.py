import unittest
from oql.query import Query


"""
python -m unittest discover oql
"""


class TestWorks(unittest.TestCase):
    def test_get_works_simple_valid(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget works\nsort by display_name asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

    def test_works_filter_publication_year(self):
        query_string = "get works where publication_year is 2020"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/works?page=1&per_page=25&sort=display_name:asc&filter=publication_year:2020"
        )
        self.assertEqual(query.oql_query(), "using works\nget works where publication_year is 2020\nsort by display_name asc\nreturn display_name, publication_year, type, primary_location.source.id, authorships.author.id, authorships.institutions.id, primary_topic.id, primary_topic.subfield.id, primary_topic.field.id, primary_topic.domain.id, sustainable_development_goals.id, open_access.oa_status")
        self.assertTrue(query.is_valid())

class TestAuthors(unittest.TestCase):
    def test_authors_valid(self):
        query_string = "get authors"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/authors?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget authors\nsort by display_name asc\nreturn display_name, display_name_alternatives, last_known_institutions.id, ids.orcid")
        self.assertTrue(query.is_valid())


class TestInstitutions(unittest.TestCase):
    def test_institutions_valid(self):
        query_string = "get institutions"
        query = Query(query_string=query_string)
        self.assertEqual(query.old_query(), "/institutions?page=1&per_page=25&sort=display_name:asc")
        self.assertEqual(query.oql_query(), "using works\nget institutions\nsort by display_name asc\nreturn display_name, type, country_code, parent_institutions, child_institutions, ids.ror")
        self.assertTrue(query.is_valid())


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
