from elasticsearch_dsl import Q


class SearchOpenAlex:
    def __init__(self, search_terms, index=None):
        self.search_terms = search_terms
        self.index = index

    def build_query(self):
        if not self.search_terms:
            query = self.match_all()
        elif self.is_phrase():
            basic_query = self.phrase_query()
            query = self.function_query(basic_query)
        elif self.index and self.index.lower().startswith("concepts"):
            basic_query = self.basic_concepts_query()
            query = self.function_query(basic_query)
        elif self.index and self.index.lower().startswith("works"):
            basic_query = self.basic_works_query()
            query = self.function_query(basic_query)
        else:
            basic_query = self.basic_query()
            query = self.function_query(basic_query)
        return query

    def basic_query(self):
        return Q(
            "match", display_name={"query": self.search_terms, "operator": "and"}
        ) | Q("match_phrase", display_name={"query": self.search_terms, "boost": 2})

    def basic_concepts_query(self):
        return (
            Q(
                "match",
                display_name={
                    "query": self.search_terms,
                    "operator": "and",
                    "boost": 1.5,
                },
            )
            | Q("match_phrase", display_name={"query": self.search_terms, "boost": 2})
            | Q("match", description={"query": self.search_terms})
        )

    def basic_works_query(self):
        return (
            Q(
                "match",
                display_name={
                    "query": self.search_terms,
                    "operator": "and",
                    "boost": 1.5,
                },
            )
            | Q("match_phrase", display_name={"query": self.search_terms, "boost": 2})
            | Q("match", abstract_inverted_index={"query": self.search_terms})
        )

    @staticmethod
    def function_query(basic_query):
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
            query=basic_query,
            boost_mode="multiply",
        )

    def phrase_query(self):
        return Q("match_phrase", display_name={"query": self.search_terms})

    @staticmethod
    def match_all():
        return Q("match_all")

    def is_phrase(self):
        return self.search_terms.startswith('"') and self.search_terms.endswith('"')
