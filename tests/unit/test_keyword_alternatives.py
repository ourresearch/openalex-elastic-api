"""Keyword display_name_alternatives in autocomplete and search (oxjob #1464).

ES is mocked: single_entity_autocomplete runs against a fake Search.execute that
captures the request body and returns canned hits. The ranking tests score the
captured function_score with a small evaluator (`_score` below) that reads the
query exactly as built, so they check that the query itself ranks an
alternative-only match just below a name match (it needs 100x the works to pass
it) and an exact alternative in the top tier, below an exact name.
"""

import math
import re
from unittest import mock

import pytest
from elasticsearch_dsl.response import Hit
from werkzeug.datastructures import MultiDict

from autocomplete.schemas import AutoCompleteSchema
from autocomplete.shared import (
    exact_match_query,
    set_matched_alternatives,
    single_entity_autocomplete,
)
from autocomplete.utils import ALTERNATIVE_MATCH, NAME_MATCH, matching_alternative
from core.search import full_search_query

KEYWORDS_INDEX = "keywords-v1"


class FakeRequest:
    def __init__(self, **args):
        self.args = MultiDict(args)


class FakeResponse(list):
    """Enough of an elasticsearch_dsl Response for single_entity_autocomplete."""

    def __init__(self, hits):
        super().__init__(hits)
        self.hits = mock.Mock()
        self.hits.total.value = len(hits)
        self.took = 1


def _hit(display_name, works_count, alternatives=None, matched=None, description=None):
    source = {
        "id": f"https://openalex.org/keywords/{display_name.replace(' ', '-')}",
        "display_name": display_name,
        "works_count": works_count,
    }
    if description is not None:
        source["description"] = description
    if alternatives is not None:
        source["display_name_alternatives"] = alternatives
    raw = {"_index": KEYWORDS_INDEX, "_id": source["id"], "_source": source}
    if matched is not None:
        raw["matched_queries"] = matched
    return Hit(raw)


def _run_autocomplete(q, hits=(), index_name=KEYWORDS_INDEX):
    """Run single_entity_autocomplete with ES mocked; return (body, result)."""
    captured = {}

    def fake_execute(search, *args, **kwargs):
        captured["body"] = search.to_dict()
        return FakeResponse(list(hits))

    with mock.patch("elasticsearch_dsl.Search.execute", fake_execute):
        result = single_entity_autocomplete({}, index_name, FakeRequest(q=q))
    return captured["body"], result


# ---- a tiny evaluator for the captured function_score -------------------------


# Deliberately independent of autocomplete.utils.matching_alternative: this
# evaluator stands in for ES's match_phrase_prefix, so it must not share code
# with the Python matcher it is checking against.
def _words(text):
    return re.findall(r"\w+", text.casefold())


def _phrase_prefix(values, q):
    q_words = _words(q)
    for value in values:
        words = _words(value)
        for start in range(len(words) - len(q_words) + 1):
            window = words[start:start + len(q_words)]
            if window[:-1] == q_words[:-1] and window[-1].startswith(q_words[-1]):
                return True
    return False


def _field_values(doc, field):
    base = field.split(".")[0]  # display_name.autocomplete -> display_name
    value = doc.get(base)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _matches(query, doc):
    (kind, body), = query.items()
    if kind == "bool":
        return any(_matches(q, doc) for q in body.get("should", []))
    if kind == "match_phrase_prefix":
        (field, spec), = body.items()
        q = spec["query"] if isinstance(spec, dict) else spec
        return _phrase_prefix(_field_values(doc, field), q)
    if kind == "term":
        (field, spec), = body.items()
        assert spec["case_insensitive"] is True
        return any(
            v.casefold() == spec["value"].casefold()
            for v in _field_values(doc, field)
        )
    raise AssertionError(f"evaluator does not know {kind}")


def _score(body, doc):
    """Score doc the way ES scores the captured function_score (boost_mode replace,
    score_mode sum); None when the candidate query does not select it."""
    function_score = body["query"]["function_score"]
    assert function_score["boost_mode"] == "replace"
    assert function_score["score_mode"] == "sum"
    if not _matches(function_score["query"], doc):
        return None
    total = 0.0
    for function in function_score["functions"]:
        if "field_value_factor" in function:
            factor = function["field_value_factor"]
            assert factor["modifier"] == "log1p"
            total += math.log10(1 + doc.get(factor["field"], factor["missing"]))
        elif _matches(function["filter"], doc):
            total += function["weight"]
    return total


def _rank(q, docs):
    body, _ = _run_autocomplete(q)
    scored = [(_score(body, d), d["display_name"]) for d in docs]
    return [name for score, name in sorted(
        (pair for pair in scored if pair[0] is not None), reverse=True
    )]


MYOCARDIAL_INFARCTION = {
    "display_name": "myocardial infarction",
    "display_name_alternatives": ["heart attack", "MI", "cardiac infarction"],
    "works_count": 270000,
}
HEART_ATTACK_PREDICTION = {
    "display_name": "heart attack prediction",
    "works_count": 623,
}
HEART_ATTACK_DETECTION = {
    "display_name": "heart attack detection",
    "works_count": 327,
}
MICE = {"display_name": "mice", "works_count": 187784}


# ---- ranking ---------------------------------------------------------------


class TestKeywordAutocompleteRanking:
    def test_alternative_match_with_100x_the_works_beats_a_name_match(self):
        # "heart att": myocardial infarction matches only through its
        # alternative "heart attack"; with 433x the works of the best name
        # match it still comes first.
        ranked = _rank(
            "heart att",
            [HEART_ATTACK_PREDICTION, HEART_ATTACK_DETECTION, MYOCARDIAL_INFARCTION],
        )
        assert ranked == [
            "myocardial infarction",
            "heart attack prediction",
            "heart attack detection",
        ]

    def test_alternative_match_with_less_than_100x_the_works_stays_below(self):
        # "social c": social change matches by name; social media matches only
        # through "social communication media" and has 1.3x the works.
        social_change = {"display_name": "social change", "works_count": 341484}
        social_media = {
            "display_name": "social media",
            "display_name_alternatives": ["social communication media"],
            "works_count": 434882,
        }
        assert _rank("social c", [social_media, social_change]) == [
            "social change", "social media"
        ]
        heart_attack_risk = dict(HEART_ATTACK_PREDICTION, works_count=2701)
        assert _rank("heart att", [MYOCARDIAL_INFARCTION, heart_attack_risk]) == [
            "heart attack prediction", "myocardial infarction"
        ]

    def test_exact_alternative_gets_the_top_tier(self):
        # "MI" exactly equals an alternative: top tier, above "mice", which
        # matches by name with fewer works... and above it even with more works.
        busy_mice = dict(MICE, works_count=10_000_000)
        ranked = _rank("mi", [busy_mice, MYOCARDIAL_INFARCTION])
        assert ranked == ["myocardial infarction", "mice"]

    def test_exact_display_name_gets_the_top_tier(self):
        heart_attack = {"display_name": "Heart Attack", "works_count": 5}
        ranked = _rank("heart attack", [HEART_ATTACK_PREDICTION, heart_attack])
        assert ranked == ["Heart Attack", "heart attack prediction"]

    def test_exact_name_beats_exact_alternative(self):
        heart_attack = {"display_name": "heart attack", "works_count": 5}
        ranked = _rank("Heart Attack", [MYOCARDIAL_INFARCTION, heart_attack])
        assert ranked == ["heart attack", "myocardial infarction"]

    def test_query_shape(self):
        body, _ = _run_autocomplete("heart att")
        function_score = body["query"]["function_score"]
        name_clause = {
            "match_phrase_prefix": {
                "display_name.autocomplete": {"query": "heart att", "_name": NAME_MATCH}
            }
        }
        alternative_clause = {
            "match_phrase_prefix": {
                "display_name_alternatives.autocomplete": {
                    "query": "heart att",
                    "_name": ALTERNATIVE_MATCH,
                }
            }
        }
        primary = {"bool": {"should": [name_clause, alternative_clause]}}
        assert function_score["query"] == primary
        exact, exact_name, tier, name_bonus, popularity = function_score["functions"]
        assert exact["weight"] == 2000000
        assert exact["filter"] == {
            "bool": {
                "should": [
                    {"term": {"display_name.keyword": {"value": "heart att", "case_insensitive": True}}},
                    {"term": {"display_name_alternatives.keyword": {"value": "heart att", "case_insensitive": True}}},
                ]
            }
        }
        assert exact_name == {
            "filter": {"term": {"display_name.keyword": {"value": "heart att", "case_insensitive": True}}},
            "weight": 100,
        }
        assert tier == {"filter": primary, "weight": 999998}
        assert name_bonus == {"filter": name_clause, "weight": 2}
        assert popularity["field_value_factor"]["field"] == "works_count"
        assert "display_name_alternatives" in body["_source"]

    def test_other_entities_keep_the_display_name_only_exact_filter(self):
        # The exact-tier filter for every other entity renders as before.
        assert exact_match_query(["display_name.keyword"], "nature").to_dict() == {
            "term": {"display_name.keyword": {"value": "nature", "case_insensitive": True}}
        }
        body, _ = _run_autocomplete("nature", index_name="sources-v3")
        exact = body["query"]["function_score"]["functions"][0]["filter"]
        assert exact == {
            "term": {"display_name.keyword": {"value": "nature", "case_insensitive": True}}
        }
        assert "display_name_alternatives" not in body["_source"]


# ---- hint ------------------------------------------------------------------


def _hints(q, hits):
    _, result = _run_autocomplete(q, hits)
    return [row["hint"] for row in AutoCompleteSchema(many=True).dump(result["results"])]


class TestKeywordAutocompleteHint:
    def test_alternative_only_match_shows_the_alternative(self):
        hits = [
            _hit(
                "myocardial infarction", 270000,
                alternatives=["cardiac infarction", "heart attack", "MI"],
                matched=[ALTERNATIVE_MATCH], description="Death of heart muscle.",
            ),
            _hit(
                "heart attack prediction", 623, alternatives=[],
                matched=[NAME_MATCH], description="Estimating heart attack risk.",
            ),
        ]
        assert _hints("heart att", hits) == [
            "heart attack", "Estimating heart attack risk."
        ]

    def test_name_and_alternative_match_keeps_the_description(self):
        hits = [
            _hit(
                "heart attack", 10, alternatives=["heart attack (disease)"],
                matched=[NAME_MATCH, ALTERNATIVE_MATCH], description="desc",
            )
        ]
        assert _hints("heart att", hits) == ["desc"]

    def test_alternative_equal_to_q_wins_over_earlier_prefix_matches(self):
        assert matching_alternative("mi", ["mitral infarct", "MI"]) == "MI"

    def test_phrase_prefix_rules(self):
        alternatives = ["acute heart attack", "attack of the heart"]
        assert matching_alternative("heart att", alternatives) == "acute heart attack"
        assert matching_alternative("heart  ATT", alternatives) == "acute heart attack"
        assert matching_alternative("att heart", alternatives) is None
        assert matching_alternative("eart", alternatives) is None
        assert matching_alternative("", alternatives) is None
        assert matching_alternative("heart", None) is None

    def test_matched_alternative_but_no_word_match_falls_back_to_description(self):
        # ES's analyzer and ours can disagree on a rare string; then the hint
        # stays the description rather than showing an unrelated alternative.
        hits = [
            _hit("x", 1, alternatives=["unrelated"], matched=[ALTERNATIVE_MATCH], description="d")
        ]
        assert _hints("heart att", hits) == ["d"]


# ---- field absent from the index (before the load) -------------------------


class TestKeywordAlternativesAbsent:
    def test_hits_without_the_field_or_named_matches_keep_description(self):
        hits = [
            _hit("heart attack prediction", 623, matched=[NAME_MATCH], description="p"),
            _hit("heart attack detection", 327, description="d"),
            _hit("heart attack symptoms", 187),
        ]
        assert _hints("heart att", hits) == ["p", "d", None]

    def test_set_matched_alternatives_ignores_hits_without_the_field(self):
        hit = _hit("x", 1, matched=[ALTERNATIVE_MATCH])
        set_matched_alternatives([hit], "x")
        assert "matched_alternative" not in hit

    def test_ranking_without_alternatives_is_by_name_then_works_count(self):
        bare_mi = {"display_name": "myocardial infarction", "works_count": 270000}
        ranked = _rank("heart att", [HEART_ATTACK_DETECTION, bare_mi, HEART_ATTACK_PREDICTION])
        assert ranked == ["heart attack prediction", "heart attack detection"]


# ---- /keywords?search= ---------------------------------------------------------


def _match_fields(query_dict):
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("match", "match_phrase") and isinstance(value, dict):
                    found.update(value.keys())
                elif key == "query_string" and isinstance(value, dict):
                    if "default_field" in value:
                        found.add(value["default_field"])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(query_dict)
    return found


class TestKeywordSearch:
    @pytest.mark.parametrize("index_name", ["keywords-v1", "keywords"])
    def test_search_covers_display_name_alternatives(self, index_name):
        query = full_search_query(index_name, "antibacterial resistance").to_dict()
        assert _match_fields(query) == {"display_name", "display_name_alternatives"}

    def test_boolean_search_covers_display_name_alternatives(self):
        query = full_search_query("keywords-v1", "antibacterial AND resistance").to_dict()
        assert _match_fields(query) == {"display_name", "display_name_alternatives"}

    def test_topics_search_unchanged(self):
        # oxjob #1307: topics-v5 keywords are objects; search their names
        query = full_search_query("topics-v5", "antibacterial resistance").to_dict()
        assert _match_fields(query) == {"display_name", "description", "keywords.display_name"}
