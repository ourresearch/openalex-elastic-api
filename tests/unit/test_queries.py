import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import (
    SearchOpenAlex,
    normalize_search_input,
    validate_search_terms,
)
from core.sort import get_sort_fields
from core.utils import map_filter_params, map_sort_params
from works.fields import fields_dict


def test_search_full(client):
    s = Search()
    search_terms = "covid-19"
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "display_name": {
                                        "query": "covid-19",
                                        "operator": "and",
                                    }
                                }
                            },
                            {
                                "match_phrase": {
                                    "display_name": {"query": "covid-19", "boost": 2}
                                }
                            },
                        ]
                    }
                },
                "boost_mode": "multiply",
            }
        }
    }


def test_search_phrase(client):
    s = Search()
    search_terms = '"covid-19"'
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {"match_phrase": {"display_name": {"query": '"covid-19"'}}},
                "boost_mode": "multiply",
            }
        }
    }


def test_search_with_display_name_sort(client):
    s = Search()
    search_terms = "covid-19"
    sort_args = "display_name"
    sort_params = map_sort_params(sort_args)
    search_oa = SearchOpenAlex(search_terms=search_terms)
    q = search_oa.build_query()
    s = s.query(q)
    sort_fields = get_sort_fields(fields_dict, None, sort_params)
    s = s.sort(*sort_fields)
    assert s.to_dict() == {
        "query": {
            "function_score": {
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "cited_by_count",
                            "factor": 1,
                            "modifier": "sqrt",
                            "missing": 1,
                        }
                    }
                ],
                "query": {
                    "bool": {
                        "should": [
                            {
                                "match": {
                                    "display_name": {
                                        "query": "covid-19",
                                        "operator": "and",
                                    }
                                }
                            },
                            {
                                "match_phrase": {
                                    "display_name": {"query": "covid-19", "boost": 2}
                                }
                            },
                        ]
                    }
                },
                "boost_mode": "multiply",
            }
        },
        "sort": ["display_name.lower"],
    }


def test_filter_range_query(client):
    s = Search()
    filter_args = "publication_year:>2015,cited_by_count:<10"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "must": [
                    {"range": {"publication_year": {"gt": 2015}}},
                    {"range": {"cited_by_count": {"lt": 10}}},
                ]
            }
        }
    }


def test_filter_regular_query(client):
    s = Search()
    filter_args = (
        "host_venue.issn:2333-3334,host_venue.publisher:null,publication_year:2020"
    )
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "must_not": [{"exists": {"field": "host_venue.publisher.lower"}}],
                "must": [
                    {"term": {"host_venue.issn.lower": "2333-3334"}},
                    {"term": {"publication_year": "2020"}},
                ],
            }
        }
    }


def test_filter_or_query(client):
    s = Search()
    filter_args = "host_venue.issn:2333-3334|5555-7777,publication_year:2020,publication_year:2021"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "should": [
                    {"term": {"host_venue.issn.lower": "2333-3334"}},
                    {"term": {"host_venue.issn.lower": "5555-7777"}},
                ],
                "minimum_should_match": 1,
                "must": [
                    {"term": {"publication_year": "2020"}},
                    {"term": {"publication_year": "2021"}},
                ],
            }
        }
    }


class TestQuotedExactFilter:
    """Quoted non-search filter values are single literal exact terms:
    operator characters inside the quotes (| * etc.) must NOT be parsed
    as OpenAlex filter syntax."""

    def test_quoted_value_with_pipe_is_single_term(self, client):
        s = Search()
        filter_args = 'raw_affiliation_strings:"Some Library | Some City"'
        filter_params = map_filter_params(filter_args)
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "authorships.raw_affiliation_strings.keyword": "Some Library | Some City"
                            }
                        }
                    ]
                }
            }
        }

    def test_quoted_value_with_wildcard_is_literal(self, client):
        s = Search()
        filter_args = 'raw_affiliation_strings:"Some * Library"'
        filter_params = map_filter_params(filter_args)
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "authorships.raw_affiliation_strings.keyword": "Some * Library"
                            }
                        }
                    ]
                }
            }
        }

    def test_unquoted_pipe_still_or_query(self, client):
        s = Search()
        filter_args = "raw_affiliation_strings:Some Library|Other Library"
        filter_params = map_filter_params(filter_args)
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "authorships.raw_affiliation_strings.keyword": [
                                    "Some Library",
                                    "Other Library",
                                ]
                            }
                        }
                    ]
                }
            }
        }

    def test_quoted_value_on_search_field_uses_search_path(self, client):
        """Search fields must keep their existing behavior: the quoted value
        is passed to SearchOpenAlex and not routed through the literal
        exact-term path on the .keyword subfield."""
        s = Search()
        filter_args = 'raw_affiliation_strings.search:"Some Library | Some City"'
        filter_params = map_filter_params(filter_args)
        s = filter_records(fields_dict, filter_params, s)
        as_str = str(s.to_dict())
        # Must not be routed to the exact .keyword term query.
        assert "authorships.raw_affiliation_strings.keyword" not in as_str
        # Must still hit the search analyzer path.
        assert "authorships.raw_affiliation_strings" in as_str

    def test_comma_inside_quoted_does_not_split_filters(self, client):
        """Comma inside a quoted exact value must not be treated as a
        filter separator, regardless of the new escape support."""
        filter_params = map_filter_params(
            'raw_affiliation_strings:"a,b",type:article'
        )
        assert filter_params == [
            {"raw_affiliation_strings": '"a,b"'},
            {"type": "article"},
        ]
        s = Search()
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "authorships.raw_affiliation_strings.keyword": "a,b"
                            }
                        },
                        {"term": {"type.lower": "article"}},
                    ]
                }
            }
        }

    def test_escaped_quotes_inside_quoted_value(self, client):
        r"""`raw_affiliation_strings:"a \"b\" c"` -> exact literal `a "b" c`."""
        filter_params = map_filter_params(
            'raw_affiliation_strings:"a \\"b\\" c"'
        )
        # The parsed value keeps the escape sequence verbatim.
        assert filter_params == [
            {"raw_affiliation_strings": '"a \\"b\\" c"'}
        ]
        s = Search()
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "authorships.raw_affiliation_strings.keyword": 'a "b" c'
                            }
                        }
                    ]
                }
            }
        }

    def test_pipe_inside_quoted_with_escaped_quotes_is_literal(self, client):
        r"""`raw_affiliation_strings:"a \"b|c\" d"` must not become an OR query."""
        filter_params = map_filter_params(
            'raw_affiliation_strings:"a \\"b|c\\" d"'
        )
        s = Search()
        s = filter_records(fields_dict, filter_params, s)
        assert s.to_dict() == {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "authorships.raw_affiliation_strings.keyword": 'a "b|c" d'
                            }
                        }
                    ]
                }
            }
        }

    def test_escaped_quotes_on_search_field_pass_through(self, client):
        r"""Search fields keep existing behavior: the value is passed to
        the search analyzer with quotes intact and is not routed through
        the literal exact-term path on `.keyword`."""
        filter_params = map_filter_params(
            'raw_affiliation_strings.search:"a \\"b\\" c"'
        )
        s = Search()
        s = filter_records(fields_dict, filter_params, s)
        as_str = str(s.to_dict())
        # Must not be routed to the exact .keyword term query.
        assert "authorships.raw_affiliation_strings.keyword" not in as_str
        # Must still hit the search analyzer path.
        assert "authorships.raw_affiliation_strings" in as_str


def test_sort_query(client):
    s = Search()
    filter_args = "host_venue.publisher:wiley,publication_year:>2015"
    sort_args = "publication_date,cited_by_count:asc,host_venue.publisher:desc"
    filter_params = map_filter_params(filter_args)
    sort_params = map_sort_params(sort_args)

    s = filter_records(fields_dict, filter_params, s)

    # sort
    sort_fields = get_sort_fields(fields_dict, None, sort_params)
    s = s.sort(*sort_fields)

    assert s.to_dict() == {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"host_venue.publisher.lower": "wiley"}},
                    {"range": {"publication_year": {"gt": 2015}}},
                ]
            }
        },
        "sort": [
            "publication_date",
            "cited_by_count",
            {"host_venue.publisher.keyword": {"order": "desc"}},
        ],
    }


# --- Wildcard detection tests ---


class TestHasWildcard:
    @pytest.mark.parametrize(
        "terms",
        [
            "machin*",
            "chem*stry",
            "wom?n",
            "roam~",
            "machine~2",
            '"climate change"~5',
        ],
    )
    def test_has_wildcard_true(self, terms):
        search_oa = SearchOpenAlex(search_terms=terms)
        assert search_oa.has_wildcard() is True

    @pytest.mark.parametrize(
        "terms",
        [
            "machine learning",
            "What is gene therapy?",
            "therapy?",
            "5 * 3",
            "covid-19",
            "hello world",
            "a*",       # too short prefix for *
            "th*",      # too short prefix for *
            "*ab",      # too short suffix for leading *
            "a~2",      # too short prefix for ~
            "go~1",     # too short prefix for ~
        ],
    )
    def test_has_wildcard_false(self, terms):
        search_oa = SearchOpenAlex(search_terms=terms)
        assert search_oa.has_wildcard() is False


class TestWildcardQueryRouting:
    def test_wildcard_produces_query_string(self):
        """Wildcard search terms should route through query_string."""
        search_oa = SearchOpenAlex(search_terms="machin*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "query_string" in q_dict
        assert q_dict["query_string"]["allow_leading_wildcard"] is False
        assert q_dict["query_string"]["query"] == "machin*"

    def test_wildcard_preserves_asterisk(self):
        """Wildcard characters should NOT be stripped from query."""
        search_oa = SearchOpenAlex(search_terms="machin*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "*" in q_dict["query_string"]["query"]

    def test_plain_search_produces_match(self):
        """Non-wildcard search should still use match + match_phrase (regression)."""
        search_oa = SearchOpenAlex(search_terms="machine learning")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "bool" in q_dict
        should = q_dict["bool"]["should"]
        query_types = [list(clause.keys())[0] for clause in should]
        assert "match" in query_types
        assert "match_phrase" in query_types

    def test_question_mark_punctuation_uses_match(self):
        """Trailing ? as punctuation should NOT trigger query_string."""
        search_oa = SearchOpenAlex(search_terms="What is gene therapy?")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "bool" in q_dict
        assert "query_string" not in q_dict

    def test_boolean_with_wildcard_preserves_wildcard(self):
        """Boolean search with wildcards should preserve the wildcard chars."""
        search_oa = SearchOpenAlex(search_terms="machin* AND learn*")
        q = search_oa.primary_match_query()
        q_dict = q.to_dict()
        assert "query_string" in q_dict
        assert "machin*" in q_dict["query_string"]["query"]
        assert "learn*" in q_dict["query_string"]["query"]

    def test_wildcard_secondary_field_query_string(self):
        """Wildcard with primary+secondary fields should produce query_string for both."""
        search_oa = SearchOpenAlex(
            search_terms="machin*",
            secondary_field="abstract",
        )
        q = search_oa.primary_secondary_match_query()
        q_dict = q.to_dict()
        should = q_dict["bool"]["should"]
        for clause in should:
            assert "query_string" in clause
            assert clause["query_string"]["allow_leading_wildcard"] is False

    def test_wildcard_tertiary_field_query_string(self):
        """Wildcard with three fields should produce query_string for all three."""
        search_oa = SearchOpenAlex(
            search_terms="machin*",
            secondary_field="abstract",
            tertiary_field="fulltext",
        )
        q = search_oa.primary_secondary_tertiary_match_query()
        q_dict = q.to_dict()
        should = q_dict["bool"]["should"]
        assert len(should) == 3
        for clause in should:
            assert "query_string" in clause
            assert clause["query_string"]["allow_leading_wildcard"] is False


SHORT_PHRASE = '"machine learning"'
LONG_PHRASE_A = '"' + ("a" * 81) + '"'
LONG_PHRASE_B = '"' + ("b" * 81) + '"'
LONG_PHRASE_C = '"' + ("c" * 81) + '"'
LONG_PHRASE_D = '"' + ("d" * 81) + '"'
LONG_PHRASE_E = '"' + ("e" * 81) + '"'
LONG_PHRASE_F = '"' + ("f" * 81) + '"'


class TestValidateSearchTerms:
    def test_empty_passes(self):
        validate_search_terms("")
        validate_search_terms(None)

    def test_plain_text_passes(self):
        validate_search_terms("machine learning neural networks")

    def test_short_phrases_or_passes(self):
        validate_search_terms(
            ' OR '.join([f'"phrase {i}"' for i in range(30)])
        )

    def test_two_long_phrases_pass(self):
        terms = ' OR '.join([LONG_PHRASE_A, LONG_PHRASE_B])
        validate_search_terms(terms)

    def test_three_long_phrases_at_boundary_pass(self):
        terms = ' OR '.join([LONG_PHRASE_A, LONG_PHRASE_B, LONG_PHRASE_C])
        validate_search_terms(terms)

    def test_four_long_phrases_rejected(self):
        terms = ' OR '.join([
            LONG_PHRASE_A, LONG_PHRASE_B, LONG_PHRASE_C, LONG_PHRASE_D,
        ])
        with pytest.raises(APIQueryParamsError) as exc:
            validate_search_terms(terms)
        assert "separate request" in str(exc.value.args[0])

    def test_six_long_phrases_rejected(self):
        terms = ' OR '.join([
            LONG_PHRASE_A, LONG_PHRASE_B, LONG_PHRASE_C,
            LONG_PHRASE_D, LONG_PHRASE_E, LONG_PHRASE_F,
        ])
        with pytest.raises(APIQueryParamsError) as exc:
            validate_search_terms(terms)
        assert "separate request" in str(exc.value.args[0])

    def test_many_short_with_few_long_passes(self):
        short = ' OR '.join([f'"q{i}"' for i in range(20)])
        long_part = ' OR '.join([LONG_PHRASE_A, LONG_PHRASE_B])
        validate_search_terms(f"{short} OR {long_part}")

    def test_phrase_at_threshold_not_counted_long(self):
        exactly_80 = '"' + ("x" * 80) + '"'
        terms = ' OR '.join([exactly_80] * 10)
        validate_search_terms(terms)

    def test_unquoted_long_strings_ignored(self):
        validate_search_terms(("z" * 500) + " OR " + ("y" * 500))


class TestSearchInputNormalization:
    """oxjob #191.2 Case 6a: curly quotes / whitespace lookalikes must not
    silently degrade phrase + boolean searches to keyword searches."""

    def test_passthrough_plain_ascii(self):
        assert normalize_search_input('"climate change"') == '"climate change"'
        assert normalize_search_input("machine learning") == "machine learning"

    def test_handles_empty_and_non_str(self):
        assert normalize_search_input("") == ""
        assert normalize_search_input(None) is None

    def test_curly_double_quotes_to_straight(self):
        assert normalize_search_input("“climate change”") == '"climate change"'

    @pytest.mark.parametrize(
        "curly",
        [
            "“climate change adaptation”",
            '“BENZYL ALCOHOL” AND (“δp” OR “δd”)',
        ],
    )
    def test_curly_phrase_detected_as_phrase(self, curly):
        """Curly-quoted query must be recognized as a phrase, not keywords."""
        assert SearchOpenAlex(search_terms=curly).has_phrase() is True

    def test_curly_phrase_query_equals_straight_phrase_query(self):
        """The whole point: curly == straight result query (no degradation)."""
        curly = SearchOpenAlex(search_terms="“climate change”").build_query()
        straight = SearchOpenAlex(search_terms='"climate change"').build_query()
        assert curly.to_dict() == straight.to_dict()

    def test_curly_boolean_detected(self):
        """Boolean operators around curly quotes still trigger boolean path."""
        oa = SearchOpenAlex(search_terms='“a” AND “b”')
        assert oa.is_boolean_search() is True
        assert oa.has_phrase() is True

    def test_apostrophe_not_treated_as_phrase(self):
        """Single curly apostrophe (children's) must NOT become a phrase."""
        oa = SearchOpenAlex(search_terms="children’s literature")
        assert oa.search_terms == "children's literature"
        assert oa.has_phrase() is False
        plain = SearchOpenAlex(search_terms="children's literature")
        assert oa.build_query().to_dict() == plain.build_query().to_dict()

    @pytest.mark.parametrize("ws", [" ", " ", " "])
    def test_space_lookalikes_become_space(self, ws):
        assert (
            normalize_search_input(f'"climate{ws}change"') == '"climate change"'
        )

    @pytest.mark.parametrize("zw", ["​", "‌", "‍", "﻿", "­"])
    def test_zero_width_chars_removed(self, zw):
        assert normalize_search_input(f"climate{zw}change") == "climatechange"
