from elasticsearch_dsl import Q


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
        elif self.is_phrase():
            phrase_query = self.primary_phrase_query()
            query = self.citation_boost_query(phrase_query)
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
        return Q(
            "match",
            **{self.primary_field: {"query": self.search_terms, "operator": "and"}},
        ) | Q(
            "match_phrase",
            **{self.primary_field: {"query": self.search_terms, "boost": 2}},
        )

    def primary_phrase_query(self):
        return Q("match_phrase", **{self.primary_field: {"query": self.search_terms}})

    def primary_secondary_match_query(self):
        """Searches primary and secondary fields."""
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
        """Searches primary, secondary, tertiary fields (used with works search param)."""
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
                        "boost": 0.05,
                    }
                },
            )
            | Q(
                "match_phrase",
                **{
                    self.tertiary_field: {
                        "query": self.search_terms,
                        "boost": 0.1,
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

    def is_phrase(self):
        return self.search_terms.startswith('"') and self.search_terms.endswith('"')


def full_search(index_name, s, search):
    if index_name.lower().startswith("authors"):
        search_oa = SearchOpenAlex(search_terms=search, is_author_name_query=True)
    elif index_name.lower().startswith("concepts"):
        search_oa = SearchOpenAlex(search_terms=search, secondary_field="description")
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
    s = s.query(search_query)
    return s


def check_is_search_query(filter_params, search):
    is_search_query = False
    if filter_params:
        for filter in filter_params:
            if (
                "abstract.search" in filter.keys()
                and filter["abstract.search"] != ""
                or "display_name.search" in filter.keys()
                and filter["display_name.search"] != ""
                or "title.search" in filter.keys()
                and filter["title.search"] != ""
                or "raw_affiliation_string.search" in filter.keys()
                and filter["raw_affiliation_string.search"] != ""
                or "fulltext.search" in filter.keys()
                and filter["fulltext.search"] != ""
            ):
                is_search_query = True
                break
    if search and search != '""':
        is_search_query = True
    return is_search_query
