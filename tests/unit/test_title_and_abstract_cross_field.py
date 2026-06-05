"""Unit tests for title_and_abstract.search cross-field Boolean semantics (oxjob #191.7).

The bug: `title_and_abstract.search` emitted two OR'd query_strings, one per field, so a
Boolean whose halves split across title↔abstract matched neither clause and was silently
dropped. The fix routes that field through `combine_fields=True`, which emits ONE
query_string over a `fields` list so each Boolean operand can match in either field.

These tests assert the emitted ES query *shape* (no ES needed) via `.to_dict()`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Mock settings so importing core.search doesn't require a real ES URL.
sys.modules["settings"] = type(sys)("settings")
sys.modules["settings"].ES_URL_WALDEN = "http://localhost:9200"

from core.search import SearchOpenAlex


BOOLEAN = '(telemetry) AND ("invasive species")'


def _to_dict(combine_fields, primary="display_name", secondary="abstract"):
    s = SearchOpenAlex(
        search_terms=BOOLEAN,
        primary_field=primary,
        secondary_field=secondary,
        combine_fields=combine_fields,
    )
    # Skip the citation-boost wrapper to assert the raw match query.
    return s.build_query(skip_citation_boost=True).to_dict()


class TestCombineFieldsOn:
    """With combine_fields=True (the title_and_abstract path)."""

    def test_single_query_string_over_fields_list(self):
        q = _to_dict(combine_fields=True)
        assert "query_string" in q, f"expected one query_string, got {q}"
        qs = q["query_string"]
        # One clause, multi-field — not two OR'd single-field clauses.
        assert qs["fields"] == ["display_name", "abstract^0.1"]
        assert "default_field" not in qs
        assert qs["default_operator"] == "AND"
        assert qs["allow_leading_wildcard"] is False
        # The full query text is preserved (full query_string parser stays intact).
        assert "telemetry" in qs["query"] and '"invasive species"' in qs["query"]

    def test_no_top_level_bool_should(self):
        # The old shape was `bool.should[query_string, query_string]`. Ensure it's gone.
        q = _to_dict(combine_fields=True)
        assert "bool" not in q

    def test_exact_variant_uses_no_stem_fields(self):
        q = _to_dict(
            combine_fields=True,
            primary="display_name.no_stem",
            secondary="abstract.no_stem",
        )
        assert q["query_string"]["fields"] == [
            "display_name.no_stem",
            "abstract.no_stem^0.1",
        ]


class TestCombineFieldsOff:
    """Default (combine_fields=False) — every other primary/secondary caller is unchanged."""

    def test_two_or_d_query_strings_preserved(self):
        q = _to_dict(combine_fields=False)
        # Old behavior: bool.should of two single-field query_strings.
        shoulds = q["bool"]["should"]
        assert len(shoulds) == 2
        fields = [s["query_string"]["default_field"] for s in shoulds]
        assert fields == ["display_name", "abstract"]
        # Secondary keeps its 0.10 boost.
        assert shoulds[1]["query_string"]["boost"] == 0.10
        # No `fields` list on the legacy path.
        assert all("fields" not in s["query_string"] for s in shoulds)
