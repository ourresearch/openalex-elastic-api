"""Unit tests for the OQO → ES translator (#306).

Translator inputs: an OQO + a fields_dict. Outputs: a single elasticsearch_dsl Q.
We snapshot-compare the emitted Q's `.to_dict()` so the test exercises both the
leaf-encoding (operator + value → URL value string) and the tree-shaping (bool
must/should/must_not) layers.

The translator is meant to be drop-in equivalent to the URL pipeline at the
leaf-level — we cross-check by also running `filter_records` on the equivalent
URL filter dict and asserting both routes produce the same Q.
"""

import json

import pytest
from elasticsearch_dsl import Q, Search

from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from query_translation.oqo import OQO, LeafFilter, BranchFilter
from query_translation.oqo_to_es import (
    oqo_to_q,
    oqo_to_search_and_filter_q,
    OQOTranslationError,
    _encode_leaf_value,
)
from works.fields import fields_dict as works_fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def url_filter_q(filter_clauses):
    """Run filter_records on a [{key: value}, ...] list, return the emitted Q."""
    s = Search()
    s = filter_records(works_fields, filter_clauses, s)
    body = s.to_dict()
    return body.get("query")


def oqo_q_body(oqo: OQO):
    """Wrap the translator's Q in a Search to get the same `.to_dict()` shape."""
    s = Search()
    q = oqo_to_q(oqo, works_fields)
    if q is not None:
        s = s.filter(q)
    return s.to_dict().get("query")


# ---------------------------------------------------------------------------
# Leaf value encoding (no ES round-trip)
# ---------------------------------------------------------------------------


class TestLeafEncoding:
    def test_is_string(self):
        assert _encode_leaf_value(LeafFilter("type", "article")) == "article"

    def test_is_null(self):
        assert _encode_leaf_value(LeafFilter("language", None)) == "null"

    def test_is_bool_true(self):
        assert _encode_leaf_value(LeafFilter("is_oa", True)) == "true"

    def test_is_bool_false(self):
        assert _encode_leaf_value(LeafFilter("is_oa", False)) == "false"

    def test_gt(self):
        assert _encode_leaf_value(LeafFilter("publication_year", 2020, ">")) == ">2020"

    def test_gte(self):
        # RangeField gte form is "N-" (trailing dash)
        assert (
            _encode_leaf_value(LeafFilter("publication_year", 2020, ">="))
            == "2020-"
        )

    def test_lt(self):
        assert (
            _encode_leaf_value(LeafFilter("cited_by_count", 100, "<")) == "<100"
        )

    def test_lte(self):
        # RangeField lte form is "-N" (leading dash)
        assert (
            _encode_leaf_value(LeafFilter("cited_by_count", 100, "<=")) == "-100"
        )

    def test_has(self):
        assert (
            _encode_leaf_value(
                LeafFilter("title.search", "covid", operator="has")
            )
            == "covid"
        )

    def test_unknown_operator_raises(self):
        with pytest.raises(OQOTranslationError):
            _encode_leaf_value(LeafFilter("type", "x", operator="weird"))

    def test_null_with_range_operator_raises(self):
        with pytest.raises(OQOTranslationError):
            _encode_leaf_value(LeafFilter("publication_year", None, operator=">"))


# ---------------------------------------------------------------------------
# Single-leaf equivalence with the URL pipeline
# ---------------------------------------------------------------------------


class TestSingleLeafEquivalence:
    """Each OQO leaf must produce the same Q as the equivalent URL filter."""

    def test_simple_term(self):
        oqo = OQO(get_rows="works", filter_rows=[LeafFilter("type", "article")])
        assert oqo_q_body(oqo) == url_filter_q([{"type": "article"}])

    def test_negation(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("type", "article", is_negated=True)],
        )
        assert oqo_q_body(oqo) == url_filter_q([{"type": "!article"}])

    def test_range_gte(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("publication_year", "2020", ">=")],
        )
        assert oqo_q_body(oqo) == url_filter_q([{"publication_year": "2020-"}])

    def test_range_gt(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("publication_year", "2020", ">")],
        )
        assert oqo_q_body(oqo) == url_filter_q([{"publication_year": ">2020"}])

    def test_range_lte(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("cited_by_count", "100", "<=")],
        )
        assert oqo_q_body(oqo) == url_filter_q([{"cited_by_count": "-100"}])

    def test_null(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("language", None)],
        )
        assert oqo_q_body(oqo) == url_filter_q([{"language": "null"}])

    def test_bool_true(self):
        oqo = OQO(get_rows="works", filter_rows=[LeafFilter("is_oa", True)])
        assert oqo_q_body(oqo) == url_filter_q([{"is_oa": "true"}])


# ---------------------------------------------------------------------------
# Top-level AND (implicit list of filters)
# ---------------------------------------------------------------------------


class TestImplicitTopLevelAnd:
    def test_two_leaves_andd_together(self):
        """Two top-level OQO leaves AND together (mirrors the URL pipeline's
        per-clause `s.filter(...)` chain).

        Note: the translator emits a single `bool.must` wrapper while the URL
        pipeline applies each clause as a separate `s.filter()`. ES treats
        `bool.filter: [a, b]` and `bool.filter: [bool.must: [a, b]]` identically,
        so we test structurally that the right two leaves are present, not byte
        equality with the URL shape.
        """
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter("type", "article"),
                LeafFilter("publication_year", "2024"),
            ],
        )
        q = oqo_to_q(oqo, works_fields)
        body = q.to_dict()
        assert "bool" in body
        must_clauses = body["bool"]["must"]
        assert len(must_clauses) == 2
        # Both leaves are term queries on the right fields.
        terms = [list(c["term"].keys())[0] for c in must_clauses if "term" in c]
        assert "type.lower" in terms or "type" in terms
        assert "publication_year" in terms


# ---------------------------------------------------------------------------
# Nested boolean trees (the differentiator vs OXURL)
# ---------------------------------------------------------------------------


class TestNestedBoolean:
    def test_or_of_two_terms(self):
        # Equivalent to URL: filter=type:article|book
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter("type", "article"),
                        LeafFilter("type", "book"),
                    ],
                )
            ],
        )
        q = oqo_to_q(oqo, works_fields)
        assert q is not None
        body = q.to_dict()
        assert "bool" in body
        # OR uses should + minimum_should_match=1
        assert "should" in body["bool"]
        assert body["bool"]["minimum_should_match"] == 1
        assert len(body["bool"]["should"]) == 2

    def test_nested_and_or_not_unrepresentable_in_url(self):
        """AND(year >= 2020, OR(inst=I1, inst=I2), NOT(retracted=true))

        OXURL can't express this nested shape — the OR-of-instutition-IDs lives
        inside an AND that also has a NOT-leaf. This is exactly the case the new
        endpoint exists to handle.
        """
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter("publication_year", "2020", ">="),
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter("institutions.id", "I136199984"),
                        LeafFilter("institutions.id", "I97018004"),
                    ],
                ),
                LeafFilter("is_retracted", True, is_negated=True),
            ],
        )
        q = oqo_to_q(oqo, works_fields)
        assert q is not None
        body = q.to_dict()
        # Top should be a bool/must with three clauses.
        assert "bool" in body
        assert "must" in body["bool"]
        assert len(body["bool"]["must"]) == 3

    def test_negated_branch(self):
        # NOT(OR(type=article, type=book))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="or",
                    filters=[
                        LeafFilter("type", "article"),
                        LeafFilter("type", "book"),
                    ],
                    is_negated=True,
                )
            ],
        )
        q = oqo_to_q(oqo, works_fields)
        body = q.to_dict()
        # Negation of a bool/should wraps as bool/must_not
        assert "bool" in body
        assert "must_not" in body["bool"]


# ---------------------------------------------------------------------------
# Empty OQO
# ---------------------------------------------------------------------------


class TestEmptyOqo:
    def test_no_filters_returns_none(self):
        oqo = OQO(get_rows="works", filter_rows=[])
        assert oqo_to_q(oqo, works_fields) is None


class TestSearchFilterSplit:
    """`oqo_to_search_and_filter_q` lifts top-level `.search` leaves into a
    scoring (query-context) Q, leaving exact filters in the filter Q — so the
    executor can score search (relevance order) like legacy (#323)."""

    def test_search_goes_to_search_q_filter_to_filter_q(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter("default.search", "quantum", operator="has"),
                LeafFilter("type", "article"),
            ],
        )
        search_q, filter_q = oqo_to_search_and_filter_q(oqo, works_fields)
        assert search_q is not None
        assert filter_q is not None
        # The exact `type` filter must NOT be in the scoring query.
        assert "article" not in str(search_q.to_dict())
        assert "article" in str(filter_q.to_dict())

    def test_pure_search_has_no_filter_q(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("default.search", "quantum", operator="has")],
        )
        search_q, filter_q = oqo_to_search_and_filter_q(oqo, works_fields)
        assert search_q is not None
        assert filter_q is None

    def test_no_search_all_in_filter_q(self):
        oqo = OQO(get_rows="works", filter_rows=[LeafFilter("type", "article")])
        search_q, filter_q = oqo_to_search_and_filter_q(oqo, works_fields)
        assert search_q is None
        assert filter_q is not None

    def test_scoring_false_keeps_search_in_filter_q(self):
        """When sampling (scoring=False), legacy applies search via s.filter —
        so everything (incl. search) goes to filter_q, search_q is None."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("default.search", "quantum", operator="has")],
        )
        search_q, filter_q = oqo_to_search_and_filter_q(
            oqo, works_fields, scoring=False
        )
        assert search_q is None
        assert filter_q is not None

    def test_negated_search_stays_in_filter_q(self):
        """A negated search leaf is not a relevance signal — keep it in filter."""
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "default.search", "quantum", operator="has", is_negated=True
                )
            ],
        )
        search_q, filter_q = oqo_to_search_and_filter_q(oqo, works_fields)
        assert search_q is None
        assert filter_q is not None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unknown_column_id_raises(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[LeafFilter("not_a_real_column_xyz", "x")],
        )
        with pytest.raises(OQOTranslationError):
            oqo_to_q(oqo, works_fields)

    def test_empty_branch_raises(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[BranchFilter(join="and", filters=[])],
        )
        with pytest.raises(OQOTranslationError):
            oqo_to_q(oqo, works_fields)

    def test_invalid_join_raises(self):
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                BranchFilter(
                    join="xor",  # not valid
                    filters=[LeafFilter("type", "article")],
                )
            ],
        )
        with pytest.raises(OQOTranslationError):
            oqo_to_q(oqo, works_fields)


# ---------------------------------------------------------------------------
# Cross-type `is in collection` execution (oxjob #363)
# ---------------------------------------------------------------------------
#
# A cross-type col_ ref (e.g. `works where author is in collection col_…`) must
# resolve to the collection's member IDs on the OQO-native execution path, just
# like the URL pre-pass (`core.filter._apply_cross_type_collection_filters`)
# does. Before #363 the OQO path read the bare `col_…` as a literal OpenAlex ID
# and matched ~zero — the regression guard below pins that the resolved terms
# clause is emitted (and equals the URL pre-pass's clause), not the old bug.


class TestCrossTypeCollectionExecution:
    def _patch_resolver(self, monkeypatch, ret):
        # Cross-type resolves via core.filter.resolve_collection (the #266 URL
        # tests patch the same site); same-type CollectionField.build_query does
        # a local `from core.collection_resolver import resolve_collection`, so
        # patch both sites to cover either path.
        monkeypatch.setattr("core.filter.resolve_collection", lambda lid: ret)
        monkeypatch.setattr(
            "core.collection_resolver.resolve_collection", lambda lid: ret
        )

    def test_cross_type_positive_resolves_to_member_terms(self, monkeypatch):
        self._patch_resolver(monkeypatch, ("authors", ["A111", "A222"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "authorships.author.id", "col_au", operator="in collection"
                )
            ],
        )
        q = oqo_to_q(oqo, works_fields)
        assert q.to_dict() == {
            "terms": {
                "authorships.author.id.lower": [
                    "https://openalex.org/A111",
                    "https://openalex.org/A222",
                ]
            }
        }

    def test_cross_type_is_not_the_old_literal_id_bug(self, monkeypatch):
        # Regression: pre-#363 this emitted a literal `term` on a mangled ID
        # (`col_a48SaZFvdS` → `A48`) and silently matched ~zero.
        self._patch_resolver(monkeypatch, ("authors", ["A111"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "authorships.author.id",
                    "col_a48SaZFvdS",
                    operator="in collection",
                )
            ],
        )
        body = json.dumps(oqo_to_q(oqo, works_fields).to_dict())
        assert "col_" not in body
        assert "/A48" not in body  # the old mangled-ID artifact
        assert "https://openalex.org/A111" in body

    def test_cross_type_parity_with_url_prepass(self, monkeypatch):
        # The OQO-native terms clause must match the URL pre-pass's clause
        # (the executor applies it via s.filter(), so the inner clause is what
        # counts). Compare the inner terms against the pre-pass body.
        self._patch_resolver(monkeypatch, ("sources", ["S123", "S456"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "primary_location.source.id",
                    "col_src",
                    operator="in collection",
                )
            ],
        )
        oqo_clause = oqo_to_q(oqo, works_fields).to_dict()
        url_body = url_filter_q([{"primary_location.source.id": "col_src"}])
        # url_body wraps the same terms clause in bool.filter (from s.filter()).
        assert url_body == {"bool": {"filter": [oqo_clause]}}

    def test_cross_type_negation_wraps_must_not(self, monkeypatch):
        self._patch_resolver(monkeypatch, ("authors", ["A1234"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "authorships.author.id",
                    "col_au",
                    operator="in collection",
                    is_negated=True,
                )
            ],
        )
        body = json.dumps(oqo_to_q(oqo, works_fields).to_dict())
        assert "must_not" in body
        assert "https://openalex.org/A1234" in body

    def test_unknown_collection_positive_matches_zero(self, monkeypatch):
        self._patch_resolver(monkeypatch, (None, []))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "authorships.author.id", "col_gone", operator="in collection"
                )
            ],
        )
        # Empty terms clause → matches zero (spec).
        assert oqo_to_q(oqo, works_fields).to_dict() == {
            "terms": {"authorships.author.id.lower": []}
        }

    def test_unknown_collection_negation_is_noop_match_all(self, monkeypatch):
        # Negating a match-zero clause yields match-all — the spec "negation of a
        # deleted collection is a no-op" behavior, reproduced via ~q.
        self._patch_resolver(monkeypatch, (None, []))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "authorships.author.id",
                    "col_gone",
                    operator="in collection",
                    is_negated=True,
                )
            ],
        )
        assert oqo_to_q(oqo, works_fields).to_dict() == {
            "bool": {"must_not": [{"terms": {"authorships.author.id.lower": []}}]}
        }

    def test_cross_type_type_mismatch_raises(self, monkeypatch):
        self._patch_resolver(monkeypatch, ("works", ["W1"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter(
                    "primary_location.source.id",
                    "col_wrong",
                    operator="in collection",
                )
            ],
        )
        with pytest.raises(APIQueryParamsError) as exc:
            oqo_to_q(oqo, works_fields)
        msg = str(exc.value)
        assert "works" in msg and "sources" in msg

    def test_same_type_collection_unaffected(self, monkeypatch):
        # Same-type `collection` column is a CollectionField that resolves
        # natively via build_query — it must NOT route through the cross-type
        # branch, and still emits a terms clause on the entity `id`.
        self._patch_resolver(monkeypatch, ("works", ["W111", "W222"]))
        oqo = OQO(
            get_rows="works",
            filter_rows=[
                LeafFilter("collection", "col_w", operator="in collection")
            ],
        )
        body = json.dumps(oqo_to_q(oqo, works_fields).to_dict())
        assert "https://openalex.org/W111" in body
        assert "https://openalex.org/W222" in body
