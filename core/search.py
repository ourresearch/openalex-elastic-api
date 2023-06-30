from elasticsearch_dsl import Q

from core.exceptions import APISearchError


class SearchOpenAlex:
    def __init__(
        self,
        search_terms,
        primary_field=None,
        secondary_field=None,
        tertiary_field=None,
        is_author_name_query=False,
    ):
        self.search_terms = search_terms
        self.primary_field = primary_field if primary_field else "display_name"
        self.secondary_field = secondary_field
        self.tertiary_field = tertiary_field
        self.is_author_name_query = is_author_name_query

    def build_query(self):
        if not self.search_terms:
            query = self.match_all()
        elif (
            self.primary_field == "authorships.raw_affiliation_string"
            and len(self.search_terms.strip()) > 3
        ):
            query_string_query = self.query_string_query()
            query = self.citation_boost_query(query_string_query)
        elif self.is_author_name_query:
            author_name_query = self.author_name_query()
            query = self.citation_boost_query(author_name_query)
        elif self.primary_field and self.secondary_field and self.tertiary_field:
            basic_query = self.primary_secondary_tertiary_match_query()
            query = self.citation_boost_query(basic_query)
        elif self.primary_field and self.secondary_field:
            basic_query = self.primary_secondary_match_query()
            query = self.citation_boost_query(basic_query)
        else:
            basic_query = self.primary_match_query()
            query = self.citation_boost_query(basic_query)
        return query

    @staticmethod
    def match_all():
        return Q("match_all")

    def query_string_query(self):
        return Q(
            "query_string",
            query=f"{self.search_terms}",
            default_operator="AND",
            default_field=self.primary_field,
        ) | Q(
            "match_phrase",
            **{self.primary_field: {"query": self.search_terms, "boost": 2}},
        )

    def primary_match_query(self):
        """Searches with 'and' and phrase queries, with phrase boosted by 2."""
        if self.is_boolean_search() or self.has_phrase():
            self.remove_wildcard_characters()
            return Q(
                "query_string",
                query=self.search_terms,
                default_field=self.primary_field,
                default_operator="AND",
            )
        else:
            return Q(
                "match",
                **{self.primary_field: {"query": self.search_terms, "operator": "and"}},
            ) | Q(
                "match_phrase",
                **{self.primary_field: {"query": self.search_terms, "boost": 2}},
            )

    def primary_secondary_match_query(self):
        """Searches primary and secondary fields."""
        if self.is_boolean_search() or self.has_phrase():
            self.remove_wildcard_characters()
            return Q(
                "query_string",
                query=self.search_terms,
                default_field=self.primary_field,
                default_operator="AND",
            ) | Q(
                "query_string",
                query=self.search_terms,
                default_field=self.secondary_field,
                boost=0.10,
                default_operator="AND",
            )
        else:
            return (
                Q(
                    "match",
                    **{
                        self.primary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 1,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{self.primary_field: {"query": self.search_terms, "boost": 2}},
                )
                | Q(
                    "match",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 0.10,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "boost": 0.15,
                        }
                    },
                )
            )

    def primary_secondary_tertiary_match_query(self):
        """Searches primary, secondary, tertiary fields."""
        if self.tertiary_field == "display_name_acronyms":
            tertiary_match_boost = 2
            tertiary_phrase_boost = 2
        else:
            tertiary_match_boost = 0.05
            tertiary_phrase_boost = 0.1

        if self.is_boolean_search() or self.has_phrase():
            self.remove_wildcard_characters()
            return (
                Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.primary_field,
                    default_operator="AND",
                )
                | Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.secondary_field,
                    boost=0.5,
                    default_operator="AND",
                )
                | Q(
                    "query_string",
                    query=self.search_terms,
                    default_field=self.tertiary_field,
                    boost=tertiary_match_boost,
                    default_operator="AND",
                )
            )
        else:
            return (
                Q(
                    "match",
                    **{
                        self.primary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 1.5,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{self.primary_field: {"query": self.search_terms, "boost": 3}},
                )
                | Q(
                    "match",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": 0.3,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.secondary_field: {
                            "query": self.search_terms,
                            "boost": 0.5,
                        }
                    },
                )
                | Q(
                    "match",
                    **{
                        self.tertiary_field: {
                            "query": self.search_terms,
                            "operator": "and",
                            "boost": tertiary_match_boost,
                        }
                    },
                )
                | Q(
                    "match_phrase",
                    **{
                        self.tertiary_field: {
                            "query": self.search_terms,
                            "boost": tertiary_phrase_boost,
                        }
                    },
                )
            )

    def author_name_query(self):
        """Search display_name and display_name.folded in order to ignore diacritics."""
        return Q(
            "multi_match",
            **{
                "query": self.search_terms,
                "fields": [self.primary_field, self.primary_field + ".folded"],
                "operator": "and",
                "type": "most_fields",
            },
        ) | Q(
            "multi_match",
            **{
                "query": self.search_terms,
                "fields": [self.primary_field, self.primary_field + ".folded"],
                "type": "phrase",
                "boost": 2,
            },
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

    def has_phrase(self):
        # search term contains two or more quotes
        return self.search_terms.count('"') >= 2

    def is_boolean_search(self):
        boolean_words = [" AND ", " OR ", " NOT "]
        return any(word in self.search_terms for word in boolean_words)

    def remove_wildcard_characters(self):
        """Remove characters used for wildcard, regex, or fuzzy search."""
        self.search_terms = (
            self.search_terms.replace("*", "").replace("?", "").replace("~", "")
        )


def full_search_query(index_name, search):
    if index_name.lower().startswith("authors"):
        search_oa = SearchOpenAlex(search_terms=search, is_author_name_query=True)
    elif index_name.lower().startswith("concepts"):
        search_oa = SearchOpenAlex(search_terms=search, secondary_field="description")
    elif index_name.lower().startswith("funders"):
        search_oa = SearchOpenAlex(
            search_terms=search,
            secondary_field="alternate_titles",
            tertiary_field="description",
        )
    elif index_name.lower().startswith("institutions"):
        search_oa = SearchOpenAlex(
            search_terms=search,
            secondary_field="display_name_alternatives",
            tertiary_field="display_name_acronyms",
        )
    elif index_name.lower().startswith("publishers"):
        search_oa = SearchOpenAlex(
            search_terms=search,
            secondary_field="alternate_titles",
        )
    elif index_name.lower().startswith("venues") or index_name.lower().startswith(
        "sources"
    ):
        search_oa = SearchOpenAlex(
            search_terms=search,
            secondary_field="alternate_titles",
            tertiary_field="abbreviated_title",
        )
    elif index_name.lower().startswith("works"):
        search_oa = SearchOpenAlex(
            search_terms=search, secondary_field="abstract", tertiary_field="fulltext"
        )
    else:
        search_oa = SearchOpenAlex(search_terms=search)
    search_query = search_oa.build_query()
    return search_query


def check_is_search_query(filter_params, search):
    search_keys = [
        "abstract.search",
        "default.search",
        "display_name.search",
        "fulltext.search",
        "raw_affiliation_string.search",
        "title.search",
    ]

    if search and search != '""':
        return True

    if filter_params:
        for filter in filter_params:
            for key in search_keys:
                if filter.get(key, "") != "":
                    return True

    return False
