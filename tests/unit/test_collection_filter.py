"""Unit tests for the `collection:` filter (oxjob #228 / collections-v1 Phase 2).

Exercises the bits that don't need a live ES cluster:
- `core.collection_resolver.resolve_collection`'s HTTP-shape contract with users-api
- `core.fields.CollectionField.build_query` (single + negated)
- `core.filter._apply_collection_filters` (intersection + entity-type validation)

Integration with the elastic-api request pipeline is covered by the existing
functional suite once a stub users-api is running.
"""
import pytest
import requests
from elasticsearch_dsl import Search

import settings
from core import collection_resolver
from core.exceptions import APIQueryParamsError, CollectionResolutionUnavailableError
from core.fields import CollectionField
from core.filter import _apply_collection_filters
from works.fields import fields_dict as works_fields_dict


class _FakeResp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


# ---------- resolve_collection ----------

class TestResolveCollection:
    def test_404_returns_none_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(
            collection_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(404),
        )
        assert collection_resolver.resolve_collection("col_deleted") == (None, [])

    def test_200_single_page(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        body = {
            "meta": {"page": 1, "per_page": 200, "total_count": 3, "total_pages": 1},
            "collection": {"entity_type": "works"},
            "entity_ids": ["W1", "W2", "W3"],
        }
        monkeypatch.setattr(
            collection_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(200, body),
        )
        etype, ids = collection_resolver.resolve_collection("col_abc")
        assert etype == "works"
        assert ids == ["W1", "W2", "W3"]

    def test_200_multi_page(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        pages = {
            1: {
                "meta": {"page": 1, "per_page": 200, "total_count": 3, "total_pages": 2},
                "collection": {"entity_type": "authors"},
                "entity_ids": ["A1", "A2"],
            },
            2: {
                "meta": {"page": 2, "per_page": 200, "total_count": 3, "total_pages": 2},
                "collection": {"entity_type": "authors"},
                "entity_ids": ["A3"],
            },
        }

        def _fake_get(url, params=None, timeout=None, headers=None):
            return _FakeResp(200, pages[params["page"]])

        monkeypatch.setattr(collection_resolver.requests, "get", _fake_get)
        etype, ids = collection_resolver.resolve_collection("col_multi")
        assert etype == "authors"
        assert ids == ["A1", "A2", "A3"]

    def test_500_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(
            collection_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(500),
        )
        with pytest.raises(CollectionResolutionUnavailableError) as exc:
            collection_resolver.resolve_collection("col_broken")
        # Public message must not leak the status code or collection id.
        assert "500" not in str(exc.value)
        assert "col_broken" not in str(exc.value)

    def test_timeout_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")

        def _raise(*a, **kw):
            # Real requests.ConnectionError messages typically include the
            # HTTPSConnectionPool hostname — that must not reach the client.
            raise requests.ConnectionError(
                "HTTPSConnectionPool(host='internal-users-api.example.com', "
                "port=443): Max retries exceeded"
            )

        monkeypatch.setattr(collection_resolver.requests, "get", _raise)
        with pytest.raises(CollectionResolutionUnavailableError) as exc:
            collection_resolver.resolve_collection("col_slow")
        # Hostname must not appear in the user-facing exception arg.
        assert "internal-users-api" not in str(exc.value)
        assert "HTTPSConnectionPool" not in str(exc.value)

    def test_missing_users_api_url_raises_query_params_error(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", None)
        with pytest.raises(APIQueryParamsError):
            collection_resolver.resolve_collection("col_anything")


# ---------- CollectionField ----------

class TestCollectionField:
    def test_positive_builds_terms(self, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: ("works", ["W1", "W2"]))
        f = CollectionField(entity_type="works")
        f.value = "col_abc"
        q = f.build_query()
        body = q.to_dict()
        # Short-form IDs from users-api are canonicalized to the full ES id URL.
        assert body == {"terms": {"id": [
            "https://openalex.org/W1",
            "https://openalex.org/W2",
        ]}}

    def test_positive_already_full_urls_passthrough(self, monkeypatch):
        monkeypatch.setattr(
            collection_resolver, "resolve_collection",
            lambda lid: ("works", [
                "https://openalex.org/W1",
                "https://openalex.org/W2",
            ]),
        )
        f = CollectionField(entity_type="works")
        f.value = "col_abc"
        q = f.build_query()
        assert q.to_dict() == {"terms": {"id": [
            "https://openalex.org/W1",
            "https://openalex.org/W2",
        ]}}

    def test_negated_wraps_not(self, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: ("works", ["W1"]))
        f = CollectionField(entity_type="works")
        f.value = "!col_abc"
        q = f.build_query()
        body = q.to_dict()
        assert "bool" in body
        assert "must_not" in body["bool"]

    def test_wrong_entity_type_rejected(self, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: ("works", ["W1"]))
        f = CollectionField(entity_type="authors")
        f.value = "col_abc"
        with pytest.raises(APIQueryParamsError) as exc:
            f.build_query()
        assert "type 'works'" in str(exc.value)
        assert "/authors" in str(exc.value)

    def test_deleted_label_matches_zero(self, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: (None, []))
        f = CollectionField(entity_type="works")
        f.value = "col_deleted"
        q = f.build_query()
        body = q.to_dict()
        assert body == {"terms": {"id": []}}

    def test_negated_deleted_label_matches_all(self, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: (None, []))
        f = CollectionField(entity_type="works")
        f.value = "!col_deleted"
        q = f.build_query()
        assert q.to_dict() == {"match_all": {}}

    def test_invalid_label_id_format_rejected(self, monkeypatch):
        f = CollectionField(entity_type="works")
        f.value = "not-a-collection"
        with pytest.raises(APIQueryParamsError):
            f.build_query()


# ---------- _apply_collection_filters (intersection) ----------

class TestApplyCollectionFilters:
    def test_single_positive_builds_one_terms_clause(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("works", ["W1", "W2"]),
        )
        s = Search()
        s, remaining = _apply_collection_filters(
            works_fields_dict, [{"collection": "col_L1"}], s,
        )
        body = s.to_dict()
        # The single terms clause is present somewhere in the filter tree.
        assert remaining == []
        assert "W1" in str(body) and "W2" in str(body)

    def test_two_positives_rejected_single_label_only(self, monkeypatch):
        # oxjob #228: multi-collection intersection removed. Two positives now 400
        # fail-fast before any resolver call.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_collection", _track)
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(
                works_fields_dict,
                [{"collection": "col_L1"}, {"collection": "col_L2"}],
                s,
            )
        assert "Only one collection" in str(exc.value)
        assert calls == []

    def test_wrong_entity_type_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("authors", ["A1"]),
        )
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(
                works_fields_dict, [{"collection": "col_Lw"}], s,
            )
        assert "type 'authors'" in str(exc.value)
        assert "/works" in str(exc.value)

    def test_unknown_label_matches_zero(self, monkeypatch):
        # Deleted/nonexistent collection → silently empty `terms` (spec).
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: (None, []),
        )
        s = Search()
        s, remaining = _apply_collection_filters(
            works_fields_dict, [{"collection": "col_gone"}], s,
        )
        body = str(s.to_dict())
        # An empty `terms` is still present (matches zero).
        assert "terms" in body
        assert remaining == []

    def test_negated_label(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("works", ["W1", "W2"]),
        )
        s = Search()
        s, remaining = _apply_collection_filters(
            works_fields_dict, [{"collection": "!col_L1"}], s,
        )
        body = str(s.to_dict())
        assert "must_not" in body
        assert "W1" in body and "W2" in body

    def test_invalid_label_id_format_rejected(self):
        s = Search()
        with pytest.raises(APIQueryParamsError):
            _apply_collection_filters(
                works_fields_dict, [{"collection": "bogus"}], s,
            )

    def test_non_label_filters_pass_through_unchanged(self):
        s = Search()
        params = [{"publication_year": "2020"}, {"is_oa": "true"}]
        s2, remaining = _apply_collection_filters(works_fields_dict, params, s)
        assert remaining == params
        # `s` should not have been touched (no filter clauses added).
        assert s2.to_dict() == s.to_dict()

    def test_too_many_labels_rejected(self, monkeypatch):
        # Single-collection cap (=1); two distinct collections 400 fail-fast.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_collection", _track)
        s = Search()
        params = [{"collection": "col_L1"}, {"collection": "col_L2"}]
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(works_fields_dict, params, s)
        assert "Only one collection" in str(exc.value)
        assert calls == []  # fail fast — no outbound resolver calls

    def test_pipe_or_within_label_value_rejected(self, monkeypatch):
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_collection", _track)
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(
                works_fields_dict, [{"collection": "col_L1|col_L2"}], s,
            )
        assert "OR (pipe)" in str(exc.value)
        assert calls == []

    def test_duplicate_labels_deduped_before_resolving(self, monkeypatch):
        # Repeated same collection dedupes to 1 = within cap.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1", "W2"])

        monkeypatch.setattr("core.filter.resolve_collection", _track)
        s = Search()
        params = [{"collection": "col_L1"}] * 12
        _apply_collection_filters(works_fields_dict, params, s)
        assert calls == ["col_L1"]

    def test_positive_plus_negative_rejected(self, monkeypatch):
        # 1 positive + 1 negative = 2 distinct, over the single-collection cap.
        monkeypatch.setattr(
            "core.filter.resolve_collection",
            lambda lid: ("works", ["W1"]),
        )
        s = Search()
        params = [{"collection": "col_P"}, {"collection": "!col_N"}]
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(works_fields_dict, params, s)
        assert "Only one collection" in str(exc.value)


# ---------- COLLECTION_ID_RE format cap ----------

class TestCollectionIdRegex:
    def test_short_id_accepted(self):
        assert CollectionField.COLLECTION_ID_RE.match("col_abc123")
        assert CollectionField.COLLECTION_ID_RE.match("!col_abc123")

    def test_max_length_id_accepted(self):
        # 48 chars after the `col_` prefix is the upper bound.
        assert CollectionField.COLLECTION_ID_RE.match("col_" + "a" * 48)

    def test_oversize_id_rejected(self):
        # 49 chars after the prefix should be rejected.
        assert not CollectionField.COLLECTION_ID_RE.match("col_" + "a" * 49)
