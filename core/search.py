from elasticsearch_dsl import Q

from core.knn import KNNQuery
import requests

from settings import ES_URL


class SearchOpenAlex:
    def __init__(
        self,
        search_terms,
        primary_field=None,
        secondary_field=None,
        tertiary_field=None,
        is_author_name_query=False,
        is_semantic_query=False,
    ):
        self.search_terms = search_terms
        self.primary_field = primary_field if primary_field else "display_name"
        self.secondary_field = secondary_field
        self.tertiary_field = tertiary_field
        self.is_author_name_query = is_author_name_query
        self.is_semantic_query = is_semantic_query

    def build_query(self):
        if not self.search_terms:
            query = self.match_all()
        elif (
            self.primary_field == "authorships.raw_affiliation_strings"
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
        elif self.is_semantic_query:
            semantic_query = self.semantic_query()
            query = self.citation_boost_query(semantic_query, scaling_type="log")
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
            self.clean_search_terms()
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
            self.clean_search_terms()
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
            self.clean_search_terms()
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
        fields = [self.primary_field, self.primary_field + ".folded"]

        if self.secondary_field:
            fields.extend([self.secondary_field, self.secondary_field + ".folded"])

        most_fields_query = Q(
            "multi_match",
            query=self.search_terms,
            fields=fields,
            operator="and",
            type="most_fields",
        )

        phrase_query = Q(
            "multi_match",
            query=self.search_terms,
            fields=fields,
            type="phrase",
            boost=2,
        )

        return most_fields_query | phrase_query

    def semantic_query(self):
        query_vector = get_vector(self.search_terms)
        knn_query = KNNQuery("vector_embedding", query_vector, 100, similarity=0.5)
        return knn_query

    @staticmethod
    def citation_boost_query(query, scaling_type="sqrt"):
        """Uses cited_by_count to boost query results with a conditional script.
        Supports two types of scaling: 'sqrt' for square root, and 'log' for logarithmic scaling.
        """
        if scaling_type == "sqrt":
            script_source = """
            if (doc['cited_by_count'].size() == 0 || doc['cited_by_count'].value == 0) {
                return 0.5;
            } else {
                return 1 + Math.sqrt(doc['cited_by_count'].value);
            }
            """
        elif scaling_type == "log":
            script_source = """
            if (doc['cited_by_count'].size() == 0 || doc['cited_by_count'].value <= 1) {
                return 0.5;
            } else {
                return 1 + Math.log(doc['cited_by_count'].value);
            }
            """
        else:
            raise ValueError("Invalid scaling_type. Choose 'sqrt' or 'log'.")

        return Q(
            "function_score",
            functions=[{"script_score": {"script": {"source": script_source}}}],
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

    def clean_search_terms(self):
        self.search_terms = (
            self.search_terms.strip()
            .replace("/", " ")
            .replace(":", " ")
            .replace("[", "")
            .replace("]", "")
        )
        if self.search_terms.lower().endswith(
            "and"
        ) or self.search_terms.lower().endswith("not"):
            self.search_terms = self.search_terms[:-3].strip()
        # strip html
        self.search_terms = self.search_terms.replace("<", "").replace(">", "")


def full_search_query(index_name, search_terms):
    if index_name.lower().startswith("authors"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="display_name_alternatives",
            is_author_name_query=True,
        )
    elif index_name.lower().startswith("concepts"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms, secondary_field="description"
        )
    elif index_name.lower().startswith("funders"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
            tertiary_field="description",
        )
    elif index_name.lower().startswith("institutions"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="display_name_alternatives",
            tertiary_field="display_name_acronyms",
        )
    elif index_name.lower().startswith("publishers"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
        )
    elif index_name.lower().startswith("topics"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="description",
            tertiary_field="keywords",
        )
    elif index_name.lower().startswith("sources"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="alternate_titles",
            tertiary_field="abbreviated_title",
        )
    elif index_name.lower().startswith("works"):
        search_oa = SearchOpenAlex(
            search_terms=search_terms,
            secondary_field="abstract",
            tertiary_field="fulltext",
        )
    elif index_name.lower().startswith("funder-search"):
        # Support wildcards for funder-search
        if '*' in search_terms or '?' in search_terms:
            # Use query_string for wildcard support
            return Q(
                "query_string",
                query=search_terms,
                default_field="html",
                default_operator="AND",
            )
        else:
            search_oa = SearchOpenAlex(
                search_terms=search_terms,
                primary_field="html",
            )
            # Skip citation boost for funder-search since it doesn't have cited_by_count
            return search_oa.primary_match_query()
    else:
        search_oa = SearchOpenAlex(search_terms=search_terms)
    search_query = search_oa.build_query()
    return search_query


def check_is_search_query(filter_params, search):
    search_keys = [
        "abstract.search",
        "default.search",
        "display_name.search",
        "fulltext.search",
        "keyword.search",
        "raw_affiliation_strings.search",
        "raw_author_name.search",
        "semantic.search",
        "title.search",
        "title_and_abstract.search",
    ]

    if search and search != '""':
        return True

    if filter_params:
        for filter in filter_params:
            for key in search_keys:
                if filter.get(key, "") != "":
                    return True

    return False


def get_vector(text):
    """
    Use the minilm-l12-v2 model to get embeddings.
    """
    url = f"{ES_URL}/_ml/trained_models/sentence-transformers__all-minilm-l12-v2/_infer"
    data = {"docs": [{"text_field": text}]}
    response = requests.post(url, json=data)
    result = response.json()["inference_results"][0]["predicted_value"]
    return result
