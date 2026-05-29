"""Unit tests for the cross-type `<entity-id-field>:col_xxx` filter (oxjob #266).

Companion to test_collection_filter.py (oxjob #228 same-type filter). Exercises
`core.filter._apply_cross_type_collection_filters` and the
`OpenAlexIDField.build_terms_query` it dispatches through.

These tests don't need a live ES/users-api cluster; resolve_collection is
monkey-patched. Run with `--noconftest` to skip the app-importing top conftest:

  pytest tests/unit/test_cross_type_collection_filter.py -q --noconftest
"""
import json

import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.fields import OpenAlexIDField
from core.filter import (
    MAX_RESOLVED_IDS_PER_REQUEST,
    _apply_cross_type_collection_filters,
)
from works.fields import fields_dict as works_fields_dict


# ---------- positive single-collection ----------

class TestPositive:
    def test_source_collection_on_works_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sources", ["S123", "S456"]),
        )
        s = Search()
        s, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"primary_location.source.id": "col_src1"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert remaining == []
        assert "primary_location.source.id" in body
        assert "https://openalex.org/S123" in body
        assert "https://openalex.org/S456" in body

    def test_author_collection_on_works_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("authors", ["A111", "A222"]),
        )
        s = Search()
        s, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"authorships.author.id": "col_au"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert remaining == []
        assert "authorships.author.id" in body
        assert "https://openalex.org/A111" in body

    def test_institutions_uses_dotted_field_name(self, monkeypatch):
        # authorships.institutions.id is the special branch in
        # OpenAlexIDField.build_terms_query that uses es_field().replace("__", ".")
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("institutions", ["I100"]),
        )
        s = Search()
        s, _ = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"authorships.institutions.id": "col_inst"}],
            s,
        )
        body = s.to_dict()
        # Verify the terms clause exists somewhere; we don't pin the exact
        # field path to avoid coupling to __lower suffix conventions.
        assert "https://openalex.org/I100" in json.dumps(body)


# ---------- TermField paths (SDGs, keywords) ----------

class TestTermFieldPaths:
    def test_sdg_collection(self, monkeypatch):
        # SDGs are TermField; the existing TermField._get_formatted_value
        # turns short "1" / "2" into the metadata.un.org URL form.
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sdgs", ["1", "2"]),
        )
        s = Search()
        s, _ = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"sustainable_development_goals.id": "col_sdg"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert "https://metadata.un.org/sdg/1" in body
        assert "https://metadata.un.org/sdg/2" in body

    def test_keywords_collection(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("keywords", ["climate-change", "renewable-energy"]),
        )
        s = Search()
        s, _ = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"keywords.id": "col_kw"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert "https://openalex.org/keywords/climate-change" in body
        assert "https://openalex.org/keywords/renewable-energy" in body


# ---------- negation ----------

class TestNegation:
    def test_negation_wraps_in_must_not(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("authors", ["A1234"]),
        )
        s = Search()
        s, _ = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"authorships.author.id": "!col_au"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert "must_not" in body
        assert "https://openalex.org/A1234" in body

    def test_negation_of_deleted_collection_is_noop(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: (None, []),
        )
        s = Search()
        s2, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"primary_location.source.id": "!col_gone"}],
            s,
        )
        # No clause added; remaining empty (we consumed the filter).
        assert remaining == []
        assert s2.to_dict() == {}


# ---------- 400 rejections ----------

class TestRejections:
    def test_type_mismatch_400(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("works", ["W1234"]),
        )
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [{"primary_location.source.id": "col_wrong"}],
                s,
            )
        msg = str(exc.value)
        assert "works" in msg
        assert "sources" in msg

    def test_unsupported_field_400(self, monkeypatch):
        # cited_by has no entity_type set — explicit cue that v1 does not
        # support cross-type collection refs on it.
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [{"cited_by": "col_foo"}],
                s,
            )
        assert "cited_by" in str(exc.value)
        assert "col_" in str(exc.value).lower()

    def test_mixed_with_literal_pipe_400(self):
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [{"primary_location.source.id": "S123|col_abc"}],
                s,
            )
        assert "mix" in str(exc.value).lower() or "single" in str(exc.value).lower()

    def test_mixed_with_literal_space_400(self):
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [{"primary_location.source.id": "S123 col_abc"}],
                s,
            )
        assert "mix" in str(exc.value).lower() or "single" in str(exc.value).lower()

    def test_multi_collection_on_same_field_400(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sources", ["S123"]),
        )
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [
                    {"primary_location.source.id": "col_a"},
                    {"primary_location.source.id": "col_b"},
                ],
                s,
            )
        assert "primary_location.source.id" in str(exc.value)


# ---------- empty / deleted collection ----------

class TestEmptyDeleted:
    def test_deleted_collection_positive_matches_zero(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: (None, []),
        )
        s = Search()
        s2, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"primary_location.source.id": "col_gone"}],
            s,
        )
        # An empty terms clause matches zero docs (spec).
        body = json.dumps(s2.to_dict())
        assert remaining == []
        assert '"terms"' in body
        assert "primary_location.source.id" in body
        assert "[]" in body

    def test_empty_resolved_collection_matches_zero(self, monkeypatch):
        # entity_type set (collection exists) but the entity_ids list is empty.
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sources", []),
        )
        s = Search()
        s2, _ = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"primary_location.source.id": "col_empty"}],
            s,
        )
        body = json.dumps(s2.to_dict())
        assert '"terms"' in body
        assert "[]" in body


# ---------- budget ----------

class TestBudget:
    def test_resolved_ids_budget_cap(self, monkeypatch):
        # Resolve a collection that returns > MAX_RESOLVED_IDS_PER_REQUEST IDs.
        big_list = [f"S{n:05d}" for n in range(MAX_RESOLVED_IDS_PER_REQUEST + 1)]
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sources", big_list),
        )
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                works_fields_dict,
                [{"primary_location.source.id": "col_huge"}],
                s,
            )
        assert "too many" in str(exc.value).lower() or str(MAX_RESOLVED_IDS_PER_REQUEST) in str(exc.value)


# ---------- passthrough ----------

class TestPassthrough:
    def test_non_collection_filters_pass_through(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("sources", ["S123"]),
        )
        s = Search()
        s, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [
                {"primary_location.source.id": "col_src"},
                {"is_oa": "true"},
                {"publication_year": "2024"},
            ],
            s,
        )
        # is_oa and publication_year are NOT consumed; only the col_xxx is.
        assert remaining == [{"is_oa": "true"}, {"publication_year": "2024"}]

    def test_unknown_field_with_collection_ref_passes_through(self):
        # The cross-type pre-pass shouldn't 400 on unknown fields — it lets
        # the main loop produce the standard "not a valid filter" error.
        s = Search()
        s, remaining = _apply_cross_type_collection_filters(
            works_fields_dict,
            [{"not_a_real_filter_at_all": "col_xxx"}],
            s,
        )
        assert remaining == [{"not_a_real_filter_at_all": "col_xxx"}]


# ---------- OpenAlexIDField.build_terms_query (direct) ----------

class TestBuildTermsQuery:
    def test_default_field(self):
        f = OpenAlexIDField(param="primary_location.source.id")
        q = f.build_terms_query(["S123", "S456"]).to_dict()
        # __lower subfield used; values canonicalized to full URL form.
        assert q == {
            "terms": {
                "primary_location.source.id.lower": [
                    "https://openalex.org/S123",
                    "https://openalex.org/S456",
                ]
            }
        }

    def test_authorships_institutions_id_special_branch(self):
        f = OpenAlexIDField(param="authorships.institutions.id")
        q = f.build_terms_query(["I100"]).to_dict()
        # Dotted field name from es_field().replace("__", ".") path.
        assert "https://openalex.org/I100" in json.dumps(q)

    def test_invalid_id_in_resolved_list_raises(self):
        f = OpenAlexIDField(param="primary_location.source.id")
        with pytest.raises(APIQueryParamsError):
            f.build_terms_query(["bogus", "S123"])


# ---------- author-side institution fields (Test 10 from #266 ACCEPTANCE.md) ----------
#
# These were missing from ENTITY_ID_PARAM_TYPES in the original Phase 3 ship —
# caught by the 2026-05-29 prod ACCEPTANCE run. We verify the map + the
# annotate_entity_types wiring directly here; the full /authors-endpoint
# request path is verified via prod ACCEPTANCE Test 10 (creating a real
# institutions collection and hitting /authors?filter=last_known_institutions.id:col_xxx).
# Importing authors.fields at this level would race with test_combined_search.py's
# module-level sys.modules['settings'] clobber, so we keep this test scoped to core/.

class TestAuthorInstitutionEntityTypeMap:
    AUTHOR_INST_FIELDS = [
        "last_known_institutions.id",
        "last_known_institutions.lineage",
        "affiliations.institution.id",
        "affiliations.institution.lineage",
    ]

    @pytest.mark.parametrize("param", AUTHOR_INST_FIELDS)
    def test_param_is_in_entity_id_param_types(self, param):
        from core.fields import ENTITY_ID_PARAM_TYPES
        assert ENTITY_ID_PARAM_TYPES.get(param) == "institutions"

    def test_annotate_entity_types_tags_the_new_fields(self):
        # Mirror what authors/fields.py does: build the field objects, call
        # annotate_entity_types, confirm each ends up with entity_type set.
        from core.fields import OpenAlexIDField, annotate_entity_types
        fields = [OpenAlexIDField(param=p) for p in self.AUTHOR_INST_FIELDS]
        annotate_entity_types(fields)
        for f in fields:
            assert f.entity_type == "institutions", (
                f"{f.param} did not get entity_type tagged"
            )

    def test_cross_type_filter_dispatches_institutions_collection(self, monkeypatch):
        # Build a minimal fields_dict locally — same shape annotate_entity_types
        # produces on a real endpoint — and run the full cross-type filter pre-pass
        # against it. Exercises core.filter end-to-end without authors/ import.
        from core.fields import OpenAlexIDField, annotate_entity_types
        fs = [OpenAlexIDField(param=p) for p in self.AUTHOR_INST_FIELDS]
        annotate_entity_types(fs)
        fields_dict = {f.param: f for f in fs}

        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("institutions", ["I100", "I200"]),
        )
        s = Search()
        s, remaining = _apply_cross_type_collection_filters(
            fields_dict,
            [{"last_known_institutions.id": "col_inst"}],
            s,
        )
        body = json.dumps(s.to_dict())
        assert remaining == []
        assert "https://openalex.org/I100" in body
        assert "https://openalex.org/I200" in body

    def test_cross_type_filter_rejects_type_mismatch_on_author_field(self, monkeypatch):
        from core.fields import OpenAlexIDField, annotate_entity_types
        fs = [OpenAlexIDField(param=p) for p in self.AUTHOR_INST_FIELDS]
        annotate_entity_types(fs)
        fields_dict = {f.param: f for f in fs}

        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("works", ["W100"]),
        )
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_cross_type_collection_filters(
                fields_dict,
                [{"last_known_institutions.id": "col_wrong"}],
                Search(),
            )
        msg = str(exc.value).lower()
        assert "institutions" in msg and "works" in msg
