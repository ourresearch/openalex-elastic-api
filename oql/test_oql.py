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


class TestQueryFilter(unittest.TestCase):
    def test_filter_publication_year(self):
        query_string = "get works where publication_year is 2020"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/works?page=1&per_page=25&filter=publication_year:2020"
        )
        self.assertEqual(query.oql_query(), "get works where publication_year is 2020")
        self.assertTrue(query.is_valid())

    def test_filter_institutions_by_country_code(self):
        query_string = "get institutions where country_code is CA"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(), "/institutions?page=1&per_page=25&filter=country_code:CA"
        )
        self.assertEqual(query.oql_query(), "get institutions where country_code is CA")
        self.assertTrue(query.is_valid())

    def test_filter_institution_by_id_return_works_count(self):
        query_string = "get institutions where id is I27837315 return works_count"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(),
            "/institutions?select=works_count&page=1&per_page=25&filter=id:I27837315",
        )
        self.assertEqual(
            query.oql_query(),
            "get institutions where id is I27837315 return works_count",
        )
        self.assertTrue(query.is_valid())

    def test_filter_invalid(self):
        query_string = "get works where pub is 2020"
        query = Query(query_string=query_string)
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_multiple_filters(self):
        query_string = "get works where publication_year is 2020, doi is 10.1234/abc"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(),
            "/works?page=1&per_page=25&filter=publication_year:2020,doi:10.1234/abc",
        )
        self.assertEqual(
            query.oql_query(),
            "get works where publication_year is 2020, doi is 10.1234/abc",
        )
        self.assertTrue(query.is_valid())

    def test_filter_return_columns(self):
        query_string = "get works where publication_year is 2020 return doi, title"
        query = Query(query_string=query_string)
        self.assertEqual(
            query.old_query(),
            "/works?select=doi,title&page=1&per_page=25&filter=publication_year:2020",
        )
        self.assertEqual(
            query.oql_query(),
            "get works where publication_year is 2020 return doi, title",
        )
        self.assertTrue(query.is_valid())


class TestQueryReturnColumns(unittest.TestCase):
    def test_valid_works_return_columns(self):
        query_string = "get works return doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/works?select=doi,title&page=1&per_page=25"
        )
        self.assertEqual(query.oql_query(), "get works return doi, title")
        self.assertTrue(query.is_valid())

    def test_valid_authors_return_columns(self):
        query_string = "get authors return id, display_name"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/authors?select=id,display_name&page=1&per_page=25"
        )
        self.assertEqual(query.oql_query(), "get authors return id, display_name")
        self.assertTrue(query.is_valid())

    def test_works_invalid_return_columns(self):
        query_string = "get works return invalid"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        self.assertIsNone(query.old_query())
        self.assertIsNone(query.oql_query())
        self.assertFalse(query.is_valid())

    def test_authors_valid_sort_and_return_columns(self):
        query_string = "get authors sort by display_name return id, display_name"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(),
            "/authors?select=id,display_name&page=1&per_page=25&sort=display_name",
        )
        self.assertEqual(
            query.oql_query(),
            "get authors sort by display_name return id, display_name",
        )
        self.assertTrue(query.is_valid())

    def test_work_invalid_sort_and_valid_return_columns(self):
        query_string = "get works sort by invalid return doi, title"
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
        query_string = "get works sort by title return doi, title"
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(), "/works?select=doi,title&page=1&per_page=25&sort=title"
        )
        self.assertEqual(query.oql_query(), "get works sort by title return doi, title")
        self.assertTrue(query.is_valid())

    def test_works_sort_by_invalid_columns(self):
        query_string = "get works sort by title return invalid"
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
        suggestions = query.autocomplete()["suggestions"]
        assert "works" in suggestions and "authors" in suggestions

    def test_works_autocomplete(self):
        query_string = "get wor"
        query = Query(query_string=query_string)
        self.assertFalse(query.is_valid())
        suggestions = query.autocomplete()["suggestions"]
        assert len(suggestions) == 1
        assert "works" in suggestions

    def test_works_autocomplete_return_columns(self):
        query_string = "get works"
        query = Query(query_string=query_string)
        suggestions = query.autocomplete()["suggestions"]
        assert "return" in suggestions


class TestExamples(unittest.TestCase):
    def test_example_1(self):
        query_string = (
            "get institutions where institution is i33213144 return count(works)"
        )
        query = Query(query_string=query_string)
        self.assertTrue(query.is_valid())
        self.assertEqual(
            query.old_query(),
            "/institutions?page=1&per_page=25&filter=institution_id:I33213144",
        )
        self.assertEqual(
            query.oql_query(),
            "get institutions where institution is i33213144 return count(works)",
        )
        self.assertTrue(query.is_valid())


if __name__ == "__main__":
    unittest.main()
