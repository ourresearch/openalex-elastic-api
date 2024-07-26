import unittest
from oql.query import Query


"""
python -m unittest discover oql
"""


class TestQueryEntity(unittest.TestCase):
    def test_get_works_valid(self):
        query_string = "list works"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "list works")
        self.assertTrue(query.is_valid())

    def test_publishers_valid(self):
        query_string = "list publishers"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/publishers?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "list publishers")
        self.assertTrue(query.is_valid())

    def test_authors_valid(self):
        query_string = "list authors"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/authors?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "list authors")
        self.assertTrue(query.is_valid())

    def test_entity_invalid(self):
        query_string = "list invalid"
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


class TestQueryFilter(unittest.TestCase):
    def test_filter_publication_year(self):
        query_string = "list works where publication_year is 2020"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/works?page=1&per_page=25&filter=publication_year:2020"
        )
        self.assertEqual(query.oql_query(), "list works where publication_year is 2020")
        self.assertTrue(query.is_valid())

    def test_filter_institutions_by_country_code(self):
        query_string = "list institutions where country_code is CA"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/institutions?page=1&per_page=25&filter=country_code:CA"
        )
        self.assertEqual(query.oql_query(), "list institutions where country_code is CA")
        self.assertTrue(query.is_valid())

    def test_filter_invalid(self):
        query_string = "list works where pub is 2020"
        query = Query(query_string=query_string)
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_multiple_filters(self):
        query_string = "list works where publication_year is 2020, doi is 10.1234/abc"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(),
            "/works?page=1&per_page=25&filter=publication_year:2020,doi:10.1234/abc",
        )
        self.assertEqual(
            query.oql_query(),
            "list works where publication_year is 2020, doi is 10.1234/abc",
        )
        self.assertTrue(query.is_valid())

    def test_filter_return_columns(self):
        query_string = (
            "list works where publication_year is 2020 return columns doi, title"
        )
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(),
            "/works?select=doi,title&page=1&per_page=25&filter=publication_year:2020",
        )
        self.assertEqual(
            query.oql_query(),
            "list works where publication_year is 2020 return columns doi, title",
        )
        self.assertTrue(query.is_valid())


class TestQueryReturnColumns(unittest.TestCase):
    def test_valid_works_return_columns(self):
        query_string = "list works return columns doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/works?select=doi,title&page=1&per_page=25"
        )
        self.assertEqual(query.oql_query(), "list works return columns doi, title")
        self.assertTrue(query.is_valid())

    def test_valid_authors_return_columns(self):
        query_string = "list authors return columns id, display_name"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/authors?select=id,display_name&page=1&per_page=25"
        )
        self.assertEqual(
            query.oql_query(), "list authors return columns id, display_name"
        )
        self.assertTrue(query.is_valid())

    def test_works_invalid_return_columns(self):
        query_string = "list works return columns invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_authors_valid_sort_and_return_columns(self):
        query_string = (
            "list authors sort by display_name return columns id, display_name"
        )
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(),
            "/authors?select=id,display_name&page=1&per_page=25&sort=display_name",
        )
        self.assertEqual(
            query.oql_query(),
            "list authors sort by display_name return columns id, display_name",
        )
        self.assertTrue(query.is_valid())

    def test_work_invalid_sort_and_valid_return_columns(self):
        query_string = "list works sort by invalid return columns doi, title"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


class TestQuerySortBy(unittest.TestCase):
    def test_works_sort_by(self):
        query_string = "list works sort by title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=title")
        self.assertEqual(query.oql_query(), "list works sort by title")
        self.assertTrue(query.is_valid())

    def test_works_sort_by_invalid(self):
        query_string = "list works sort by invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_works_sort_by_before_return_columns(self):
        query_string = "list works sort by title return columns doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/works?select=doi,title&page=1&per_page=25&sort=title"
        )
        self.assertEqual(
            query.oql_query(), "list works sort by title return columns doi, title"
        )
        self.assertTrue(query.is_valid())

    def test_works_sort_by_invalid_columns(self):
        query_string = "list works sort by title return columns invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())


class TestQueryAutocomplete(unittest.TestCase):
    def test_get_autocomplete(self):
        query_string = "list"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        suggestions = query.autocomplete()["suggestions"]
        assert "works" in suggestions and "authors" in suggestions

    def test_works_autocomplete(self):
        query_string = "list wor"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        suggestions = query.autocomplete()["suggestions"]
        assert len(suggestions) == 1
        assert "works" in suggestions

    def test_works_autocomplete_return_columns(self):
        query_string = "list works"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()["suggestions"]
        assert "return columns" in suggestions


if __name__ == "__main__":
    unittest.main()
