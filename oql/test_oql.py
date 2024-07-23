import unittest
from oql.query import Query


"""
python -m unittest discover oql
"""


class TestQueryEntity(unittest.TestCase):
    def test_get_works_valid(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get works")
        self.assertTrue(query.is_valid())

    def test_publishers_valid(self):
        query_string = "get publishers"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/publishers?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get publishers")
        self.assertTrue(query.is_valid())

    def test_authors_valid(self):
        query_string = "get authors"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/authors?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get authors")
        self.assertTrue(query.is_valid())

    def test_entity_invalid(self):
        query_string = "get invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_entity_invalid_verb(self):
        query_string = "inva"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_entity_partial_very_short(self):
        query_string = "g"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


class TestQueryReturnColumns(unittest.TestCase):
    def test_valid_works_return_columns(self):
        query_string = "get works return columns doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?select=doi,title&page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get works return columns doi, title")
        self.assertTrue(query.is_valid())

    def test_valid_authors_return_columns(self):
        query_string = "get authors return columns id, display_name"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/authors?select=id,display_name&page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get authors return columns id, display_name")
        self.assertTrue(query.is_valid())

    def test_works_invalid_return_columns(self):
        query_string = "get works return columns invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_authors_valid_sort_and_return_columns(self):
        query_string = "get authors sort by display_name return columns id, display_name"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/authors?select=id,display_name&page=1&per_page=25&sort=display_name")
        self.assertEqual(query.oql_query(), "get authors sort by display_name return columns id, display_name")
        self.assertTrue(query.is_valid())

    def test_work_invalid_sort_and_valid_return_columns(self):
        query_string = "get works sort by invalid return columns doi, title"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


class TestQuerySortBy(unittest.TestCase):
    def test_works_sort_by(self):
        query_string = "get works sort by title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=title")
        self.assertEqual(query.oql_query(), "get works sort by title")
        self.assertTrue(query.is_valid())

    def test_works_sort_by_invalid(self):
        query_string = "get works sort by invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_works_sort_by_before_return_columns(self):
        query_string = "get works sort by title return columns doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?select=doi,title&page=1&per_page=25&sort=title")
        self.assertEqual(query.oql_query(), "get works sort by title return columns doi, title")
        self.assertTrue(query.is_valid())

    def test_works_sort_by_invalid_columns(self):
        query_string = "get works sort by title return columns invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


class TestQueryAutocomplete(unittest.TestCase):
    def test_get_autocomplete(self):
        query_string = "get"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        suggestions = query.autocomplete()['suggestions']
        assert "works" in suggestions and "authors" in suggestions

    def test_works_autocomplete(self):
        query_string = "get wor"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        suggestions = query.autocomplete()['suggestions']
        assert len(suggestions) == 1
        assert "works" in suggestions

    def test_works_autocomplete_return_columns(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "return columns" in suggestions


if __name__ == "__main__":
    unittest.main()
