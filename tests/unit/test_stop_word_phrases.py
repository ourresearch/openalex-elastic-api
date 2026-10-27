"""Stop words inside quotes count (oxjob #1883).

The stemmed works text fields drop Lucene's English stop words, so a quoted phrase of
stop words matched nothing ("To be or not to be": 0 titles vs 3,844 exact) and a stop
word inside a phrase matched any word ("vitamin A deficiency" 23,738 vs 3,142). Such
phrases now run on the title/abstract `.no_stem` subfields through query_string's
quote_field_suffix, and a plain search of only stop words ("It") runs on those fields.
Searches that read fulltext (search=, fulltext.search) are left as they were (cost).

Shape tests only (no ES): `.to_dict()` of the emitted query.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:  # the real settings when they load; a stub only for the ES URL otherwise
    import settings  # noqa: F401
except Exception:
    sys.modules["settings"] = type(sys)("settings")
    sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.keyword_search import STOP_EN
from core.search import SearchOpenAlex, needs_exact_phrase, only_stop_words


def _q(terms, primary="display_name", secondary=None, tertiary=None, combine=False, works=True):
    s = SearchOpenAlex(
        search_terms=terms,
        primary_field=primary,
        secondary_field=secondary,
        tertiary_field=tertiary,
        combine_fields=combine,
        works_text=works,
    )
    return s.build_query(skip_citation_boost=True).to_dict()


def _query_strings(node):
    out = []
    if isinstance(node, dict):
        if "query_string" in node:
            out.append(node["query_string"])
        for v in node.values():
            out += _query_strings(v)
    elif isinstance(node, list):
        for v in node:
            out += _query_strings(v)
    return out


def _fields(node):
    """Every field name a match / match_phrase / multi_match clause reads."""
    out = set()
    if isinstance(node, dict):
        for kind in ("match", "match_phrase"):
            if kind in node:
                out |= set(node[kind].keys())
        if "multi_match" in node:
            out |= {f.split("^")[0] for f in node["multi_match"]["fields"]}
        for v in node.values():
            out |= _fields(v)
    elif isinstance(node, list):
        for v in node:
            out |= _fields(v)
    return out


def test_stop_list_is_lucenes_english_set():
    assert len(STOP_EN) == 33
    assert {"a", "to", "be", "or", "not", "such", "as", "it", "is", "there", "no"} <= STOP_EN


class TestDetection:
    def test_short_phrase_with_stop_word(self):
        assert needs_exact_phrase('"To be or not to be"')
        assert needs_exact_phrase('"vitamin A deficiency"')
        assert needs_exact_phrase('cancer AND "quality of life"')
        assert needs_exact_phrase('"the effect of exercise on the quality of life"')  # 4 content words

    def test_long_phrase_keeps_stemmed_field(self):
        # a pasted title is pinned down by its own words
        assert not needs_exact_phrase('"IL-38 reprograms macrophage metabolism to restrain NLRP3"')
        assert not needs_exact_phrase('"quality of life of patients with chronic kidney disease"')

    def test_phrase_without_stop_word(self):
        assert not needs_exact_phrase('"machine learning"')
        assert not needs_exact_phrase("to be or not to be")  # not quoted
        assert not needs_exact_phrase('"it\'s complicated"')  # it's is one token

    def test_only_stop_words(self):
        assert only_stop_words("It")
        assert only_stop_words("To be")
        assert not only_stop_words("To be continued")
        assert not only_stop_words("")


class TestQuotedPhrases:
    def test_title_phrase_with_stop_words_uses_no_stem(self):
        qs = _query_strings(_q('"To be or not to be"'))
        assert qs and all(q.get("quote_field_suffix") == ".no_stem" for q in qs)

    def test_title_phrase_without_stop_words_unchanged(self):
        qs = _query_strings(_q('"machine learning"'))
        assert qs and all("quote_field_suffix" not in q for q in qs)

    def test_title_and_abstract_phrase(self):
        qs = _query_strings(_q('"not at all"', secondary="abstract", combine=True))
        assert len(qs) == 1
        assert qs[0]["fields"] == ["display_name", "abstract^0.1"]
        assert qs[0]["quote_field_suffix"] == ".no_stem"

    def test_fulltext_search_unchanged(self):
        # search= / fulltext.search read fulltext, whose .no_stem phrases cost 5x the ES time
        for combine in (True, False):
            qs = _query_strings(
                _q('"vitamin A deficiency"', secondary="abstract", tertiary="fulltext", combine=combine)
            )
            assert qs and all("quote_field_suffix" not in q for q in qs)

    def test_abstract_phrase(self):
        qs = _query_strings(_q('"not at all"', primary="abstract"))
        assert qs and all(q["quote_field_suffix"] == ".no_stem" for q in qs)

    def test_boolean_with_stop_word_phrase(self):
        qs = _query_strings(_q('"quality of life" AND cancer'))
        assert qs and qs[0]["quote_field_suffix"] == ".no_stem"

    def test_non_works_index_unchanged(self):
        qs = _query_strings(_q('"journal of the"', works=False))
        assert qs and all("quote_field_suffix" not in q for q in qs)

    def test_other_fields_unchanged(self):
        # raw affiliation strings, entity alternates: no .no_stem sibling to fall back to
        qs = _query_strings(_q('"University of Oxford"', primary="display_name", secondary="alternate_titles"))
        assert qs and all("quote_field_suffix" not in q for q in qs)

    def test_exact_search_unchanged(self):
        qs = _query_strings(_q('"To be or not to be"', primary="display_name.no_stem"))
        assert qs and all("quote_field_suffix" not in q for q in qs)


class TestStopWordsOnly:
    def test_plain_stop_words_run_on_no_stem(self):
        assert _fields(_q("To be")) == {"display_name.no_stem"}

    def test_plain_stop_words_title_and_abstract(self):
        f = _fields(_q("It", secondary="abstract", combine=True))
        assert f == {"display_name.no_stem", "abstract.no_stem"}

    def test_plain_stop_words_with_fulltext_unchanged(self):
        f = _fields(_q("It", secondary="abstract", tertiary="fulltext", combine=True))
        assert f == {"display_name", "abstract", "fulltext"}

    def test_plain_with_a_content_word_unchanged(self):
        assert _fields(_q("To be continued")) == {"display_name"}

    def test_negated_stop_words(self):
        q = _q("NOT it")
        assert "display_name.no_stem" in json.dumps(q)

    def test_non_works_unchanged(self):
        assert _fields(_q("The", works=False)) == {"display_name"}
