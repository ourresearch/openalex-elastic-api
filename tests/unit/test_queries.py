import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.search import (
    SearchOpenAlex,
    normalize_search_input,
    validate_search_terms,
    validate_wildcards,
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


def test_filter_or_query_with_null():
    # `null` inside an OR-list must become a missing/exists clause, not a
    # literal "null" term that matches zero docs. Regression for oxjob #299
    # (language:en|null silently returned the same set as language:en).
    s = Search()
    filter_args = "language:en|null"
    filter_params = map_filter_params(filter_args)
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "filter": [
                    {
                        "bool": {
                            "should": [
                                {"terms": {"language.lower": ["en"]}},
                                {
                                    "bool": {
                                        "must_not": [
                                            {"exists": {"field": "language.lower"}}
                                        ]
                                    }
                                },
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                ]
            }
        }
    }


def test_filter_or_query_null_only():
    # An OR-list that is all `null` collapses to a single missing clause.
    s = Search()
    filter_params = map_filter_params("language:null|null")
    s = filter_records(fields_dict, filter_params, s)
    assert s.to_dict() == {
        "query": {
            "bool": {
                "filter": [
                    {"bool": {"must_not": [{"exists": {"field": "language.lower"}}]}}
                ]
            }
        }
    }


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

    def test_validate_search_terms_rejects_leading_wildcard(self):
        with pytest.raises(APIQueryParamsError):
            validate_search_terms("*phone")


class TestValidateWildcards:
    """oxjob #337: unsupported wildcard shapes must fail loud + kind, not reach ES
    as a raw parse error (leading) or silently degrade to a literal (short prefix)."""

    def test_empty_and_non_str_pass(self):
        validate_wildcards("")
        validate_wildcards(None)
        validate_wildcards(123)

    def test_plain_text_passes(self):
        validate_wildcards("machine learning")

    def test_supported_wildcards_pass(self):
        # trailing >=3-char prefix, mid-word, single-char ?
        validate_wildcards("phone*")
        validate_wildcards("behavi*or")
        validate_wildcards("wom?n")
        validate_wildcards("title contains chem*stry")

    def test_trailing_question_mark_passes(self):
        # a real "?" used as punctuation is not a leading/short wildcard
        validate_wildcards("what is this?")
        validate_wildcards("why? because")

    def test_bare_star_and_question_pass(self):
        # length-1 tokens are not treated as wildcards today; don't newly reject them
        validate_wildcards("who * what")
        validate_wildcards("who ? what")

    @pytest.mark.parametrize("terms", ["*phone", "?cycle", "*cycle", "find *phone now"])
    def test_leading_wildcard_rejected(self, terms):
        with pytest.raises(APIQueryParamsError) as exc:
            validate_wildcards(terms)
        assert "Leading wildcard" in str(exc.value.args[0])

    @pytest.mark.parametrize("terms", ["ab*", "a*", "ab*cd", "go ab* now"])
    def test_short_prefix_wildcard_rejected(self, terms):
        with pytest.raises(APIQueryParamsError) as exc:
            validate_wildcards(terms)
        assert "at least 3 leading characters" in str(exc.value.args[0])

    @pytest.mark.parametrize("terms", ['"bar*"', '"smart phone*"', '"wom?n"'])
    def test_wildcard_in_quotes_rejected(self, terms):
        with pytest.raises(APIQueryParamsError) as exc:
            validate_wildcards(terms)
        assert "quoted phrase" in str(exc.value.args[0])

    def test_abc_star_passes_but_ab_star_fails(self):
        validate_wildcards("abc*")  # 3-char prefix ok
        with pytest.raises(APIQueryParamsError):
            validate_wildcards("ab*")

    @pytest.mark.parametrize("terms", ['"smart phone*"~3', '"smart wom?n"~3'])
    def test_wildcard_in_quoted_proximity_passes(self, terms):
        # oxjob #355: a wildcard inside a quoted PROXIMITY phrase is supported (it
        # compiles to an ES intervals query), so validation must NOT reject it.
        validate_wildcards(terms)

    @pytest.mark.parametrize(
        "terms,needle",
        [
            ('"smart *phone"~3', "Leading wildcard"),
            ('"smart ab*"~3', "at least 3 leading characters"),
        ],
    )
    def test_bad_wildcard_shape_in_proximity_still_rejected(self, terms, needle):
        # #337's leading / short-prefix rejections still apply inside a proximity phrase.
        with pytest.raises(APIQueryParamsError) as exc:
            validate_wildcards(terms)
        assert needle in str(exc.value.args[0])


class TestProximityWildcard:
    """oxjob #355: `"smart phone*"~3` (wildcard inside a quoted proximity phrase) must
    compile to an ES `intervals` query — query_string silently drops the wildcard."""

    def test_has_proximity_wildcard_true(self):
        assert SearchOpenAlex(search_terms='"smart phone*"~3').has_proximity_wildcard()
        assert SearchOpenAlex(search_terms='"smart wom?n"~3').has_proximity_wildcard()

    @pytest.mark.parametrize(
        "terms",
        ['"smart phone"~3', "phone*", "machine learning", '"smart phone*"', "smart*"],
    )
    def test_has_proximity_wildcard_false(self, terms):
        # plain proximity, plain wildcard, plain text, wildcard-in-quotes-without-prox,
        # and a bare wildcard token all stay off the intervals path.
        assert not SearchOpenAlex(search_terms=terms).has_proximity_wildcard()

    def test_builds_intervals_with_prefix_rule(self):
        oa = SearchOpenAlex(
            search_terms='"smart phone*"~3', primary_field="display_name.no_stem"
        )
        q = oa.build_query(skip_citation_boost=True).to_dict()
        field = q["intervals"]["display_name.no_stem"]
        all_of = field["all_of"]
        assert all_of["ordered"] is False
        assert all_of["max_gaps"] == 3  # max_gaps maps 1:1 to slop N (spike-pinned)
        assert all_of["intervals"] == [
            {"match": {"query": "smart"}},
            {"prefix": {"prefix": "phone"}},
        ]

    def test_midword_question_mark_uses_wildcard_rule(self):
        oa = SearchOpenAlex(
            search_terms='"smart wom?n"~3', primary_field="display_name"
        )
        rules = oa.build_query(skip_citation_boost=True).to_dict()[
            "intervals"]["display_name"]["all_of"]["intervals"]
        assert rules[1] == {"wildcard": {"pattern": "wom?n"}}

    def test_combine_fields_ors_with_boost(self):
        # title_and_abstract.search.exact path: primary + secondary, OR'd, secondary boosted.
        oa = SearchOpenAlex(
            search_terms='"smart phone*"~3',
            primary_field="display_name.no_stem",
            secondary_field="abstract.no_stem",
            combine_fields=True,
        )
        q = oa.build_query(skip_citation_boost=True).to_dict()
        should = q["bool"]["should"]
        assert len(should) == 2
        assert "display_name.no_stem" in should[0]["intervals"]
        sec = should[1]["intervals"]["abstract.no_stem"]
        assert sec["boost"] == 0.10
        assert "query_string" not in str(q)  # wildcard NOT dropped to query_string


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
