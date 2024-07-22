import unittest
from oql.query import Query


"""
python -m unittest discover oql
"""


class TestQueryEntity(unittest.TestCase):
    def test_get_entity(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25")
        self.assertEqual(query.oql_query(), "get works")


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

    def test_works_return_columns_extended(self):
        query_string = "get works return"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "return columns" in suggestions

    def test_works_sort_by_autocomplete_1(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "sort by" in suggestions

    def test_works_sort_by_autocomplete_2(self):
        query_string = "get works sort"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "sort by" in suggestions

    def test_works_sort_by_autocomplete_3(self):
        query_string = "get works sort by"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "publication_year" in suggestions

    def test_works_sort_by_autocomplete_4(self):
        query_string = "get works sort by pub"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()['suggestions']
        assert "publication_year" in suggestions and len(suggestions) == 1

    def test_works_sort_by_valid(self):
        query_string = "get works sort by publication_year"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.oql_query(), "get works sort by publication_year")

    def test_works_sort_by_query(self):
        query_string = "get works sort by publication_year"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(query.oql_query(), "get works sort by publication_year")
        self.assertEqual(query.old_query(), "/works?page=1&per_page=25&sort=publication_year")


if __name__ == "__main__":
    unittest.main()
