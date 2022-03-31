from elasticsearch_dsl import Q


class SearchOpenAlex:
    def __init__(self, search_terms, index_full_search=None):
        self.search_terms = search_terms
        self.index_full_search = index_full_search

    def build_query(self):
        if not self.search_terms:
            query = self.match_all()
        elif self.is_phrase():
            phrase_query = self.phrase_query()
            query = self.citation_boost_query(phrase_query)
        elif self.index_full_search and self.index_full_search.lower().startswith(
            "concepts"
        ):
            full_query = self.full_query("description")
            query = self.citation_boost_query(full_query)
        elif self.index_full_search and self.index_full_search.lower().startswith(
            "works"
        ):
            full_query = self.full_query("abstract_inverted_index")
            query = self.citation_boost_query(full_query)
        else:
            basic_query = self.basic_query()
            query = self.citation_boost_query(basic_query)
        return query

    @staticmethod
    def match_all():
        return Q("match_all")

    def is_phrase(self):
        return self.search_terms.startswith('"') and self.search_terms.endswith('"')

    def basic_query(self):
        """Searches display_name only."""
        return Q(
            "match", display_name={"query": self.search_terms, "operator": "and"}
        ) | Q("match_phrase", display_name={"query": self.search_terms, "boost": 2})

    def full_query(self, field_name):
        """Searches display_name plus a second field."""
        second_field_args = {
            field_name: {"query": self.search_terms, "operator": "and", "boost": 0.10}
        }
        return (
            Q(
                "match",
                display_name={
                    "query": self.search_terms,
                    "operator": "and",
                    "boost": 1,
                },
            )
            | Q("match_phrase", display_name={"query": self.search_terms, "boost": 2})
            | Q("match", **second_field_args)
        )

    @staticmethod
    def citation_boost_query(query):
        """Uses cited_by_count to boost query results."""
        return Q(
            "function_score",
            functions={
                "field_value_factor": {
                    "field": "cited_by_count",
                    "factor": 1,
                    "modifier": "sqrt",
                    "missing": 1,
                }
            },
            query=query,
            boost_mode="multiply",
        )

    def phrase_query(self):
        return Q("match_phrase", display_name={"query": self.search_terms})
