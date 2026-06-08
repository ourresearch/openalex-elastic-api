"""Unit tests for plain (non-Boolean) multi-word cross-field search (oxjob #399).

Sibling of #191.7. #191.7 made the *Boolean* path of `title_and_abstract.search`
cross-field via `combine_fields=True`. This job extends `combine_fields` so the
*plain* (non-Boolean, non-phrase, non-wildcard) multi-word path also goes cross-field,
AND adds the same support to the 3-field `primary_secondary_tertiary_match_query`
(default.search / fulltext.search) for BOTH its Boolean and plain branches — so
`a b` == `a AND b` == two-filter on every fan-out works search column.

Key shape choices (verified live on works-v33, see job EXPLORE):
- Plain path is ADDITIVE: the original same-field clauses (per-field `match operator=and`
  + `match_phrase`) are kept, and ONE `multi_match type=cross_fields, operator=and` clause
  is OR'd on top for the extra cross-field recall. Keeping the same-field clauses preserves
  ranking (same-field docs score as before; cross-field-only matches join the tail);
  same_field ⊆ cross_fields so the union's recall == boolean == two-filter exactly.
  cross_fields is ANALYZED, so special-char literals like `c++` are safe — NOT query_string
  (the plain path never runs clean_search_terms(), so query_string would mis-parse them).
- Boolean path (3-field) -> ONE query_string over a `fields` list (mirrors #191.7, replace).
- All gated behind `combine_fields`; the entity searches that share these functions
  never set the flag, so they stay same-field.

Asserts the emitted ES query *shape* via `.to_dict()` (no ES needed).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Mock settings so importing core.search doesn't require a real ES URL.
sys.modules["settings"] = type(sys)("settings")
sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.search import SearchOpenAlex  # noqa: E402


PLAIN = "machine learning"  # no operators / quotes / wildcards -> the `else` branch


def _two_field(terms, combine_fields, primary="display_name", secondary="abstract"):
    s = SearchOpenAlex(
        search_terms=terms,
        primary_field=primary,
        secondary_field=secondary,
        combine_fields=combine_fields,
    )
    return s.build_query(skip_citation_boost=True).to_dict()


def _three_field(terms, combine_fields,
                 primary="display_name", secondary="abstract", tertiary="fulltext"):
    s = SearchOpenAlex(
        search_terms=terms,
        primary_field=primary,
        secondary_field=secondary,
        tertiary_field=tertiary,
        combine_fields=combine_fields,
    )
    return s.build_query(skip_citation_boost=True).to_dict()


class TestPlainTwoFieldCrossField:
    """Plain multi-word on title_and_abstract (display_name + abstract)."""

    def test_uses_cross_fields_multi_match(self):
        q = _two_field(PLAIN, combine_fields=True)
        clauses = q["bool"]["should"]
        mm = [c for c in clauses if "multi_match" in c]
        assert len(mm) == 1, f"expected exactly one cross-field multi_match, got {q}"
        mm = mm[0]["multi_match"]
        assert mm["type"] == "cross_fields"
        assert mm["operator"] == "and"
        assert mm["fields"] == ["display_name", "abstract^0.1"]
        assert mm["query"] == PLAIN

    def test_keeps_match_phrase_boosts(self):
        # Ranking boosts preserved: a phrase boost on each field (recall change only).
        q = _two_field(PLAIN, combine_fields=True)
        phrases = [c["match_phrase"] for c in q["bool"]["should"] if "match_phrase" in c]
        assert any("display_name" in p and p["display_name"]["boost"] == 2 for p in phrases)
        assert any("abstract" in p and p["abstract"]["boost"] == 0.15 for p in phrases)

    def test_additive_keeps_same_field_match_and_clauses(self):
        # Additive design: the per-field `match` (operator=and) clauses are KEPT (so
        # same-field docs keep their ranking); the cross_fields clause is added on top.
        q = _two_field(PLAIN, combine_fields=True)
        match_and = [
            c["match"] for c in q["bool"]["should"]
            if "match" in c and list(c["match"].values())[0].get("operator") == "and"
        ]
        fields = {list(m.keys())[0] for m in match_and}
        assert fields == {"display_name", "abstract"}, q

    def test_special_char_uses_cross_fields_not_query_string(self):
        # `c++` must be analyzed, not parsed: no query_string anywhere on the plain path.
        q = _two_field("c++", combine_fields=True)
        assert "query_string" not in str(q), f"plain path must not use query_string: {q}"
        assert any("multi_match" in c for c in q["bool"]["should"])


class TestPlainThreeFieldCrossField:
    """Plain multi-word on default.search / fulltext.search (display_name + abstract + fulltext)."""

    def test_uses_cross_fields_over_three_fields(self):
        q = _three_field(PLAIN, combine_fields=True)
        mm = [c for c in q["bool"]["should"] if "multi_match" in c]
        assert len(mm) == 1, f"expected one cross-field multi_match, got {q}"
        mm = mm[0]["multi_match"]
        assert mm["type"] == "cross_fields"
        assert mm["operator"] == "and"
        assert mm["fields"] == ["display_name^1.5", "abstract^0.3", "fulltext^0.05"]

    def test_keeps_all_three_match_phrase_boosts(self):
        q = _three_field(PLAIN, combine_fields=True)
        phrases = [c["match_phrase"] for c in q["bool"]["should"] if "match_phrase" in c]
        assert any("display_name" in p and p["display_name"]["boost"] == 3 for p in phrases)
        assert any("abstract" in p and p["abstract"]["boost"] == 0.5 for p in phrases)
        assert any("fulltext" in p and p["fulltext"]["boost"] == 0.1 for p in phrases)


class TestBooleanThreeFieldCrossField:
    """Boolean path on the 3-field columns now also cross-field (was 3 OR'd query_strings)."""

    def test_single_query_string_over_fields_list(self):
        q = _three_field('(telemetry) AND ("invasive species")', combine_fields=True)
        assert "query_string" in q, f"expected ONE query_string, got {q}"
        qs = q["query_string"]
        assert qs["fields"] == ["display_name", "abstract^0.5", "fulltext^0.05"]
        assert "default_field" not in qs
        assert qs["default_operator"] == "AND"
        assert qs["allow_leading_wildcard"] is False

    def test_not_three_or_d_query_strings(self):
        q = _three_field('(telemetry) AND ("invasive species")', combine_fields=True)
        assert "bool" not in q  # the old shape was bool.should[qs, qs, qs]


class TestExactNoStemVariants:
    """`.exact` columns use the no_stem fields with the same cross-field shapes."""

    def test_plain_three_field_no_stem(self):
        q = _three_field(
            PLAIN, combine_fields=True,
            primary="display_name.no_stem", secondary="abstract.no_stem",
            tertiary="fulltext.no_stem",
        )
        mm = [c for c in q["bool"]["should"] if "multi_match" in c][0]["multi_match"]
        assert mm["fields"] == [
            "display_name.no_stem^1.5", "abstract.no_stem^0.3", "fulltext.no_stem^0.05",
        ]

    def test_plain_two_field_no_stem(self):
        q = _two_field(
            PLAIN, combine_fields=True,
            primary="display_name.no_stem", secondary="abstract.no_stem",
        )
        mm = [c for c in q["bool"]["should"] if "multi_match" in c][0]["multi_match"]
        assert mm["fields"] == ["display_name.no_stem", "abstract.no_stem^0.1"]


class TestCombineFieldsOffUnchanged:
    """combine_fields=False (every shared entity-search caller) keeps same-field shape."""

    def test_two_field_plain_legacy_per_field_match_and(self):
        q = _two_field(PLAIN, combine_fields=False)
        clauses = q["bool"]["should"]
        # Legacy: per-field match(operator=and) + match_phrase, OR'd. No multi_match.
        assert all("multi_match" not in c for c in clauses), q
        match_and = [c["match"] for c in clauses if "match" in c]
        fields = {list(m.keys())[0] for m in match_and}
        assert fields == {"display_name", "abstract"}
        for m in match_and:
            assert list(m.values())[0]["operator"] == "and"

    def test_three_field_plain_legacy_six_clauses(self):
        q = _three_field(PLAIN, combine_fields=False)
        clauses = q["bool"]["should"]
        assert all("multi_match" not in c for c in clauses), q
        # 3 match(and) + 3 match_phrase = 6 clauses, same-field.
        assert len(clauses) == 6
        match_and = [c["match"] for c in clauses if "match" in c]
        assert {list(m.keys())[0] for m in match_and} == {
            "display_name", "abstract", "fulltext",
        }

    def test_three_field_boolean_legacy_three_or_d_query_strings(self):
        q = _three_field('(telemetry) AND ("invasive species")', combine_fields=False)
        should = q["bool"]["should"]
        assert len(should) == 3
        assert all("query_string" in s for s in should)
        assert [s["query_string"]["default_field"] for s in should] == [
            "display_name", "abstract", "fulltext",
        ]


class TestSingleWordUnchangedRecall:
    """A single word is 'in any field' either way -> still routes through the plain branch
    but cross_fields over one term == the old per-field OR (recall identical; verified live)."""

    def test_single_word_uses_cross_fields(self):
        q = _three_field("telemetry", combine_fields=True)
        mm = [c for c in q["bool"]["should"] if "multi_match" in c]
        assert len(mm) == 1 and mm[0]["multi_match"]["operator"] == "and"
