"""oxjob #1327: a pasted title's `?` is a question mark, not a wildcard.

Before, every `?` counted as a wildcard: on the default search #364's gate answered 400
("Wildcards (* or ?) require exact (no-stem) search") to titles like "Should we ditch
impact factors?", and on the exact search (Zendesk 24904) the title's last word ran as a
wildcard and missed the paper. Now a `?` is a wildcard inside a word (`wom?n`), and at
the end of a word only in a one-word or Boolean search (`psoriati?`, #570). Also:
`Oncology*Biology*Physics` in a plain stemmed search ORs in its words-only reading, so
/sources?search=International Journal of Radiation Oncology*Biology*Physics finds it.
No ES: the keyword lookup is stubbed.
"""
import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import handle_or_query
from core.search import (
    SearchOpenAlex,
    full_search_query,
    wildcard_chars_as_punctuation,
    validate_top_level_search_wildcard,
    validate_wildcard_requires_exact,
)
from core.shared_view import build_search_value_query
from works.fields import fields_dict

TITLE = "Should we ditch impact factors?"
SCRIBBR = "Does the Presence of Institutional Investors Influence Accruals Management?"


@pytest.fixture(autouse=True)
def no_keyword_lookup(monkeypatch):
    import core.keyword_search as ks
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: [] for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


def _same(a, b):
    return a.to_dict() == b.to_dict()


class TestQuestionMarksAsPunctuation:
    @pytest.mark.parametrize(
        "given, expected",
        [
            (TITLE, "Should we ditch impact factors"),
            ("How to assess severe burnout? Cutoff points", "How to assess severe burnout Cutoff points"),
            ("Plus libres sans les garçons ? Une analyse", "Plus libres sans les garçons  Une analyse"),
            ('Risk "Rocking the Boat"? A Blended', 'Risk "Rocking the Boat" A Blended'),
            ("¿Una revolución más en la ciencia?", "¿Una revolución más en la ciencia"),
            ('"What is life?"', '"What is life"'),
            ("Hallucination‐Free? Assessing", "Hallucination‐Free Assessing"),
            ("What? is wom?n life?", "What is wom?n life"),
            ("堆肥と化学肥料、何が違う?(上)", "堆肥と化学肥料、何が違う(上)"),  # no spaces in Japanese
            ("같은 자연어 문장을 해석은 없을까?", "같은 자연어 문장을 해석은 없을까"),
            # an uppercase AND in a title: still a title (one client retried this 39 times)
            ("Can Coding Agents Produce Patches That Are Correct, Secure AND Efficient?",
             "Can Coding Agents Produce Patches That Are Correct, Secure AND Efficient"),
            ("psoriati? AND skin", "psoriati AND skin"),
            ("NOT dog?", "NOT dog"),
            # a lone `*` is a footnote mark
            ("Journalism Education Yun Hao 1, * , Yuxin Lin2", "Journalism Education Yun Hao 1,  , Yuxin Lin2"),
            ("* KIKO MILANO. (2026). The KIKO Show", "KIKO MILANO. (2026). The KIKO Show"),
            ("HYPOXIA-INDUCIBLE FACTORS 1 AND 2 *", "HYPOXIA-INDUCIBLE FACTORS 1 AND 2"),
            # beside a quote too: ES answered these HTTP 500 (oxjob #1889)
            ('"Prof. *"', '"Prof. "'),
            ('"cancer research *"', '"cancer research "'),
            ('"* cancer"', '" cancer"'),
            ('"cancer **" AND dog', '"cancer " AND dog'),
            ('"*"', '""'),  # matches nothing, as before
        ],
    )
    def test_punctuation_is_dropped(self, given, expected):
        assert wildcard_chars_as_punctuation(given) == expected

    @pytest.mark.parametrize(
        "terms",
        [
            "wom?n", "wo??n", "behavio?r", "M?ller", "colo?r AND dog",  # inside a word
            "psoriati?", "Really??", '"psoriati?"',  # word-final in a one-word search
            "?cycle", "some ?cycle",  # start of a word: the validators refuse it
            "machin* learning", "chem*stry", "Nanoring**", '"canc* research"',  # `*` touching a word
        ],
    )
    def test_a_wildcard_stays(self, terms):
        assert wildcard_chars_as_punctuation(terms) == terms

    def test_as_text_overrides_the_guess(self):
        # The OQL parser checks a run of bare words one word at a time.
        assert wildcard_chars_as_punctuation("factors?", as_text=True) == "factors"
        assert wildcard_chars_as_punctuation("factors?", as_text=False) == "factors?"

    @pytest.mark.parametrize(
        "terms",
        [
            "https://www.google.com/url?opi=89978449&q=x",
            "see www.bing.com/search?q=aniko+press",
            "index https://pmc.ncbi.nlm.nih.gov/articles/PMC11739531/?utm_source",
        ],
    )
    def test_question_mark_inside_a_url_is_its_separator(self, terms):
        assert "?" not in wildcard_chars_as_punctuation(terms)

    def test_a_search_of_only_punctuation_stays_non_empty(self):
        # An empty string would build match_all (every record); a blank matches
        # nothing, like `search=.` does today.
        assert wildcard_chars_as_punctuation("?") == " "
        assert wildcard_chars_as_punctuation("*") == " "
        assert wildcard_chars_as_punctuation(" ?? ") == " "

    @pytest.mark.parametrize("terms", [None, "", "machine learning", "machin*"])
    def test_no_question_mark_is_unchanged(self, terms):
        assert wildcard_chars_as_punctuation(terms) == terms

    @pytest.mark.parametrize("terms", [TITLE, "What? is wom?n life?", "?", "psoriati?"])
    def test_idempotent(self, terms):
        once = wildcard_chars_as_punctuation(terms)
        assert wildcard_chars_as_punctuation(once) == once


class TestValidators:
    @pytest.mark.parametrize("terms", ["wom?n", "wo??n", "studies*", "aggregat* OR calibrat*"])
    def test_a_real_wildcard_still_needs_the_exact_search(self, terms):
        with pytest.raises(APIQueryParamsError, match="exact"):
            validate_top_level_search_wildcard(terms, "works-v39", is_exact=False)
        with pytest.raises(APIQueryParamsError, match="title.search.exact"):
            validate_wildcard_requires_exact("title.search", terms, "works-v39")


class TestBuilder:
    def test_stemmed_title_builds_the_same_query_as_without_the_mark(self):
        assert _same(
            SearchOpenAlex(TITLE, primary_field="display_name").build_query(),
            SearchOpenAlex("Should we ditch impact factors", primary_field="display_name").build_query(),
        )

    def test_exact_title_builds_the_same_query_as_without_the_mark(self):
        # Zendesk 24904: the last word ran as a wildcard (`management?`) and missed.
        assert _same(
            SearchOpenAlex(SCRIBBR, primary_field="display_name.no_stem").build_query(),
            SearchOpenAlex(SCRIBBR[:-1], primary_field="display_name.no_stem").build_query(),
        )

    def test_quoted_title_with_question_mark_is_a_phrase_not_a_wildcard(self):
        # Before: an intervals `wildcard` rule `factors?` on the stemmed field -> 0 hits.
        body = str(SearchOpenAlex(f'"{TITLE}"').build_query(skip_citation_boost=True).to_dict())
        assert "intervals" not in body and "?" not in body

    def test_exact_search_keeps_the_one_word_trailing_wildcard_from_570(self):
        oa = SearchOpenAlex("psoriati?", primary_field="display_name.no_stem")
        assert oa.search_terms == "psoriati?" and oa.has_wildcard()

    def test_double_question_mark_inside_a_word_is_a_wildcard_on_any_field(self):
        assert SearchOpenAlex("wo??n", secondary_field="alternate_titles").has_wildcard()

    def test_semantic_search_text_is_untouched(self):
        assert SearchOpenAlex("what is life?", is_semantic_query=True).search_terms == "what is life?"


class TestDoors:
    @pytest.mark.parametrize(
        "terms, clean",
        [
            (TITLE, "Should we ditch impact factors"),
            ("Normalité de la libido (andropause) ? (4)", "Normalité de la libido (andropause)  (4)"),
            ("Mehr Demokratie durch Volksentscheid?", "Mehr Demokratie durch Volksentscheid"),
            ("Challenge validation. https://www.google.com/url?opi=89978449&q=https://x",
             "Challenge validation. https://www.google.com/url opi=89978449&q=https://x"),
            ("Patches That Are Correct, Secure AND Efficient?", "Patches That Are Correct, Secure AND Efficient"),
            ("Journalism Education Yun Hao 1, * , Yuxin Lin2", "Journalism Education Yun Hao 1,  , Yuxin Lin2"),
        ],
    )
    @pytest.mark.parametrize("scope, stype", [(None, None), ("title", "default"),
                                              (None, "exact"), ("title_and_abstract", "exact")])
    def test_param_door_title_equals_the_title_without_its_question_marks(self, terms, clean, scope, stype):
        got = build_search_value_query("works", terms, scope, stype, skip_citation_boost=True)
        want = build_search_value_query("works", clean, scope, stype, skip_citation_boost=True)
        assert _same(got, want)

    def test_param_door_question_mark_alone_is_not_an_error(self):
        build_search_value_query("works", "?", None, None)

    def test_param_door_exact_search_keeps_the_one_word_wildcard(self):
        got = build_search_value_query("works", "psoriati?", None, "exact", skip_citation_boost=True)
        assert "psoriati?" in str(got.to_dict())

    @pytest.mark.parametrize("terms", ["wom?n", "psoriati?"])
    def test_param_door_still_rejects_a_wildcard_on_the_stemmed_search(self, terms):
        with pytest.raises(APIQueryParamsError, match="search.exact"):
            build_search_value_query("works", terms, None, None)

    @pytest.mark.parametrize(
        "param", ["title.search", "title_and_abstract.search", "abstract.search", "title.search.exact",
                  "title_and_abstract.search.exact"],
    )
    def test_filter_door_title_equals_the_title_without_the_mark(self, param):
        def built(value):
            return handle_or_query(fields_dict[param], {}, Search(), value, sample=None).to_dict()

        assert built(SCRIBBR) == built(SCRIBBR[:-1])

    def test_filter_door_exact_field_keeps_the_one_word_wildcard(self):
        q = handle_or_query(fields_dict["title.search.exact"], {}, Search(), "psoriati?", sample=None)
        assert "psoriati?" in str(q.to_dict())


class TestEcho:
    """The URL's OQL echo reads a title's `?` the same way, so the echo runs the same query."""

    @pytest.mark.parametrize(
        "column, value",
        [("fulltext.search", TITLE), ("title_and_abstract.search.exact", SCRIBBR),
         ("display_name.search", f'"{TITLE}"')],
    )
    def test_url_parser_drops_a_titles_question_mark(self, column, value):
        from query_translation.url_parser import parse_single_filter

        def leaves(f):
            return [f] if hasattr(f, "value") else [x for g in f for x in leaves(g)]

        parsed = parse_single_filter(column, value, "works")
        got = leaves(parsed if isinstance(parsed, list) else [parsed])
        want = parse_single_filter(column, wildcard_chars_as_punctuation(value), "works")
        assert all("?" not in leaf.value for leaf in got)
        assert got == leaves(want if isinstance(want, list) else [want])

    def test_url_parser_keeps_a_one_word_wildcard(self):
        from query_translation.url_parser import parse_single_filter

        assert parse_single_filter("fulltext.search.exact", "psoriati?", "works").value == "psoriati?"


class TestWordsJoinedByStar:
    NAME = "International Journal of Radiation Oncology*Biology*Physics"

    def test_sources_search_ors_in_the_words_only_reading(self):
        q = str(full_search_query("sources-v3", self.NAME).to_dict())
        assert "International Journal of Radiation Oncology Biology Physics" in q
        assert "Oncology*Biology*Physics" in q  # the as-typed wildcard reading stays

    def test_infix_wildcard_still_runs_as_typed(self):
        oa = SearchOpenAlex("chem*stry", secondary_field="alternate_titles")
        assert oa.words_joined_by_star() == "chem stry"
        assert "chem*stry" in str(oa.build_query().to_dict())

    @pytest.mark.parametrize(
        "terms, kw",
        [
            (NAME, {"primary_field": "display_name.no_stem"}),  # exact: wildcard is the point
            ("Oncology*Biology AND physics", {}),  # Boolean
            ('"Oncology*Biology"', {}),  # quoted
            ("machin* learning", {}),  # trailing wildcard, not between words
        ],
    )
    def test_no_words_only_reading(self, terms, kw):
        assert SearchOpenAlex(terms, **kw).words_joined_by_star() is None
