"""Unit tests for the `label:` filter (oxjob #228 / labels-v1 Phase 2).

Exercises the bits that don't need a live ES cluster:
- `core.label_resolver.resolve_label`'s HTTP-shape contract with users-api
- `core.fields.LabelField.build_query` (single + negated)
- `core.filter._apply_label_filters` (intersection + entity-type validation)

Integration with the elastic-api request pipeline is covered by the existing
functional suite once a stub users-api is running.
"""
import pytest
import requests
from elasticsearch_dsl import Search

import settings
from core import label_resolver
from core.exceptions import APIQueryParamsError, LabelResolutionUnavailableError
from core.fields import LabelField
from core.filter import _apply_label_filters
from works.fields import fields_dict as works_fields_dict


class _FakeResp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


# ---------- resolve_label ----------

class TestResolveLabel:
    def test_404_returns_none_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(
            label_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(404),
        )
        assert label_resolver.resolve_label("label-deleted") == (None, [])

    def test_200_single_page(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        body = {
            "meta": {"page": 1, "per_page": 200, "total_count": 3, "total_pages": 1},
            "label": {"entity_type": "works"},
            "entity_ids": ["W1", "W2", "W3"],
        }
        monkeypatch.setattr(
            label_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(200, body),
        )
        etype, ids = label_resolver.resolve_label("label-abc")
        assert etype == "works"
        assert ids == ["W1", "W2", "W3"]

    def test_200_multi_page(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        pages = {
            1: {
                "meta": {"page": 1, "per_page": 200, "total_count": 3, "total_pages": 2},
                "label": {"entity_type": "authors"},
                "entity_ids": ["A1", "A2"],
            },
            2: {
                "meta": {"page": 2, "per_page": 200, "total_count": 3, "total_pages": 2},
                "label": {"entity_type": "authors"},
                "entity_ids": ["A3"],
            },
        }

        def _fake_get(url, params=None, timeout=None, headers=None):
            return _FakeResp(200, pages[params["page"]])

        monkeypatch.setattr(label_resolver.requests, "get", _fake_get)
        etype, ids = label_resolver.resolve_label("label-multi")
        assert etype == "authors"
        assert ids == ["A1", "A2", "A3"]

    def test_500_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(
            label_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(500),
        )
        with pytest.raises(LabelResolutionUnavailableError) as exc:
            label_resolver.resolve_label("label-broken")
        # Public message must not leak the status code or label id.
        assert "500" not in str(exc.value)
        assert "label-broken" not in str(exc.value)

    def test_timeout_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")

        def _raise(*a, **kw):
            # Real requests.ConnectionError messages typically include the
            # HTTPSConnectionPool hostname — that must not reach the client.
            raise requests.ConnectionError(
                "HTTPSConnectionPool(host='internal-users-api.example.com', "
                "port=443): Max retries exceeded"
            )

        monkeypatch.setattr(label_resolver.requests, "get", _raise)
        with pytest.raises(LabelResolutionUnavailableError) as exc:
            label_resolver.resolve_label("label-slow")
        # Hostname must not appear in the user-facing exception arg.
        assert "internal-users-api" not in str(exc.value)
        assert "HTTPSConnectionPool" not in str(exc.value)

    def test_missing_users_api_url_raises_query_params_error(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", None)
        with pytest.raises(APIQueryParamsError):
            label_resolver.resolve_label("label-anything")


# ---------- LabelField ----------

class TestLabelField:
    def test_positive_builds_terms(self, monkeypatch):
        monkeypatch.setattr(label_resolver, "resolve_label",
                            lambda lid: ("works", ["W1", "W2"]))
        f = LabelField(entity_type="works")
        f.value = "label-abc"
        q = f.build_query()
        body = q.to_dict()
        # Short-form IDs from users-api are canonicalized to the full ES id URL.
        assert body == {"terms": {"id": [
            "https://openalex.org/W1",
            "https://openalex.org/W2",
        ]}}

    def test_positive_already_full_urls_passthrough(self, monkeypatch):
        monkeypatch.setattr(
            label_resolver, "resolve_label",
            lambda lid: ("works", [
                "https://openalex.org/W1",
                "https://openalex.org/W2",
            ]),
        )
        f = LabelField(entity_type="works")
        f.value = "label-abc"
        q = f.build_query()
        assert q.to_dict() == {"terms": {"id": [
            "https://openalex.org/W1",
            "https://openalex.org/W2",
        ]}}

    def test_negated_wraps_not(self, monkeypatch):
        monkeypatch.setattr(label_resolver, "resolve_label",
                            lambda lid: ("works", ["W1"]))
        f = LabelField(entity_type="works")
        f.value = "!label-abc"
        q = f.build_query()
        body = q.to_dict()
        assert "bool" in body
        assert "must_not" in body["bool"]

    def test_wrong_entity_type_rejected(self, monkeypatch):
        monkeypatch.setattr(label_resolver, "resolve_label",
                            lambda lid: ("works", ["W1"]))
        f = LabelField(entity_type="authors")
        f.value = "label-abc"
        with pytest.raises(APIQueryParamsError) as exc:
            f.build_query()
        assert "type 'works'" in str(exc.value)
        assert "/authors" in str(exc.value)

    def test_deleted_label_matches_zero(self, monkeypatch):
        monkeypatch.setattr(label_resolver, "resolve_label",
                            lambda lid: (None, []))
        f = LabelField(entity_type="works")
        f.value = "label-deleted"
        q = f.build_query()
        body = q.to_dict()
        assert body == {"terms": {"id": []}}

    def test_negated_deleted_label_matches_all(self, monkeypatch):
        monkeypatch.setattr(label_resolver, "resolve_label",
                            lambda lid: (None, []))
        f = LabelField(entity_type="works")
        f.value = "!label-deleted"
        q = f.build_query()
        assert q.to_dict() == {"match_all": {}}

    def test_invalid_label_id_format_rejected(self, monkeypatch):
        f = LabelField(entity_type="works")
        f.value = "not-a-label"
        with pytest.raises(APIQueryParamsError):
            f.build_query()


# ---------- _apply_label_filters (intersection) ----------

class TestApplyLabelFilters:
    def test_single_positive_builds_one_terms_clause(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_label",
            lambda lid: ("works", ["W1", "W2"]),
        )
        s = Search()
        s, remaining = _apply_label_filters(
            works_fields_dict, [{"label": "label-L1"}], s,
        )
        body = s.to_dict()
        # The single terms clause is present somewhere in the filter tree.
        assert remaining == []
        assert "W1" in str(body) and "W2" in str(body)

    def test_two_positives_rejected_single_label_only(self, monkeypatch):
        # oxjob #228: multi-label intersection removed. Two positives now 400
        # fail-fast before any resolver call.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_label", _track)
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_label_filters(
                works_fields_dict,
                [{"label": "label-L1"}, {"label": "label-L2"}],
                s,
            )
        assert "Only one label" in str(exc.value)
        assert calls == []

    def test_wrong_entity_type_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_label",
            lambda lid: ("authors", ["A1"]),
        )
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_label_filters(
                works_fields_dict, [{"label": "label-Lw"}], s,
            )
        assert "type 'authors'" in str(exc.value)
        assert "/works" in str(exc.value)

    def test_unknown_label_matches_zero(self, monkeypatch):
        # Deleted/nonexistent label → silently empty `terms` (spec).
        monkeypatch.setattr(
            "core.filter.resolve_label",
            lambda lid: (None, []),
        )
        s = Search()
        s, remaining = _apply_label_filters(
            works_fields_dict, [{"label": "label-gone"}], s,
        )
        body = str(s.to_dict())
        # An empty `terms` is still present (matches zero).
        assert "terms" in body
        assert remaining == []

    def test_negated_label(self, monkeypatch):
        monkeypatch.setattr(
            "core.filter.resolve_label",
            lambda lid: ("works", ["W1", "W2"]),
        )
        s = Search()
        s, remaining = _apply_label_filters(
            works_fields_dict, [{"label": "!label-L1"}], s,
        )
        body = str(s.to_dict())
        assert "must_not" in body
        assert "W1" in body and "W2" in body

    def test_invalid_label_id_format_rejected(self):
        s = Search()
        with pytest.raises(APIQueryParamsError):
            _apply_label_filters(
                works_fields_dict, [{"label": "bogus"}], s,
            )

    def test_non_label_filters_pass_through_unchanged(self):
        s = Search()
        params = [{"publication_year": "2020"}, {"is_oa": "true"}]
        s2, remaining = _apply_label_filters(works_fields_dict, params, s)
        assert remaining == params
        # `s` should not have been touched (no filter clauses added).
        assert s2.to_dict() == s.to_dict()

    def test_too_many_labels_rejected(self, monkeypatch):
        # Single-label cap (=1); two distinct labels 400 fail-fast.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_label", _track)
        s = Search()
        params = [{"label": "label-L1"}, {"label": "label-L2"}]
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_label_filters(works_fields_dict, params, s)
        assert "Only one label" in str(exc.value)
        assert calls == []  # fail fast — no outbound resolver calls

    def test_pipe_or_within_label_value_rejected(self, monkeypatch):
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1"])

        monkeypatch.setattr("core.filter.resolve_label", _track)
        s = Search()
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_label_filters(
                works_fields_dict, [{"label": "label-L1|label-L2"}], s,
            )
        assert "OR (pipe)" in str(exc.value)
        assert calls == []

    def test_duplicate_labels_deduped_before_resolving(self, monkeypatch):
        # Repeated same label dedupes to 1 = within cap.
        calls = []

        def _track(lid):
            calls.append(lid)
            return ("works", ["W1", "W2"])

        monkeypatch.setattr("core.filter.resolve_label", _track)
        s = Search()
        params = [{"label": "label-L1"}] * 12
        _apply_label_filters(works_fields_dict, params, s)
        assert calls == ["label-L1"]

    def test_positive_plus_negative_rejected(self, monkeypatch):
        # 1 positive + 1 negative = 2 distinct, over the single-label cap.
        monkeypatch.setattr(
            "core.filter.resolve_label",
            lambda lid: ("works", ["W1"]),
        )
        s = Search()
        params = [{"label": "label-P"}, {"label": "!label-N"}]
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_label_filters(works_fields_dict, params, s)
        assert "Only one label" in str(exc.value)


# ---------- LABEL_ID_RE format cap ----------

class TestLabelIdRegex:
    def test_short_id_accepted(self):
        assert LabelField.LABEL_ID_RE.match("label-abc123")
        assert LabelField.LABEL_ID_RE.match("!label-abc123")

    def test_max_length_id_accepted(self):
        # 48 chars after the `label-` prefix is the upper bound.
        assert LabelField.LABEL_ID_RE.match("label-" + "a" * 48)

    def test_oversize_id_rejected(self):
        # 49 chars after the prefix should be rejected.
        assert not LabelField.LABEL_ID_RE.match("label-" + "a" * 49)
