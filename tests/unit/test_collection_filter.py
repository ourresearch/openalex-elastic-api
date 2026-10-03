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
from elasticsearch_dsl import Q, Search

import settings
from core import collection_resolver
from core.exceptions import (
    APIQueryParamsError,
    CollectionNotFoundError,
    CollectionResolutionUnavailableError,
    CollectionTooBigToFilterError,
)
from core.fields import CollectionField
from core.filter import _apply_collection_filters
from works.fields import fields_dict as works_fields_dict


def _not_found(lid):
    raise CollectionNotFoundError(f"Collection {lid} not found.")



class _FakeResp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def _member_ids_body(entity_type, ids):
    """users-api's GET /collections/{id}/member-ids answer (oxjob #1527)."""
    return {"id": "col_x", "entity_type": entity_type, "member_count": len(ids), "member_ids": ids}


# ---------- resolve_collection ----------

class TestResolveCollection:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_no_access_raises_not_found_or_not_found(self, monkeypatch, status):
        # Missing, deleted and private all answer the same loud 404 (oxjob #646).
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(
            collection_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(status),
        )
        with pytest.raises(CollectionNotFoundError) as e:
            collection_resolver.resolve_collection("col_deleted")
        assert e.value.code == 404
        assert str(e.value) == "Collection col_deleted not found."

    def test_sends_resolver_key_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        monkeypatch.setattr(settings, "COLLECTION_RESOLVER_KEY", "k")
        seen = {}
        def fake_get(url, params=None, headers=None, timeout=None):
            seen.update(headers or {})
            return _FakeResp(200, _member_ids_body("works", ["W1"]))
        monkeypatch.setattr(collection_resolver.requests, "get", fake_get)
        collection_resolver.resolve_collection("col_x")
        assert seen.get("X-Collection-Resolver-Key") == "k"

    def test_200_one_call(self, monkeypatch):
        # One call returns every ID (oxjob #1527), with the live limit as `max`.
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append((url, params))
            return _FakeResp(200, _member_ids_body("works", ["W1", "W2", "W3"]))

        monkeypatch.setattr(collection_resolver.requests, "get", fake_get)
        etype, ids = collection_resolver.resolve_collection("col_abc")
        assert etype == "works"
        assert ids == ["W1", "W2", "W3"]
        assert calls == [(
            "http://users-api.test/collections/col_abc/member-ids",
            {"max": collection_resolver.LIVE_FILTER_LIMIT},
        )]

    @pytest.mark.parametrize("etype, count", [("authors", 100_001), ("sources", 300_001), ("works", 1_000_000)])
    def test_over_the_live_limit_is_too_big(self, monkeypatch, etype, count):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        # Over `max`, users-api sends the count and no IDs; an author collection
        # between 100,000 and 300,000 arrives with its IDs and is refused here.
        body = {"id": "col_big", "entity_type": etype, "member_count": count}
        if count <= collection_resolver.LIVE_FILTER_LIMIT:
            body["member_ids"] = [f"A{i}" for i in range(count)]
        monkeypatch.setattr(collection_resolver.requests, "get", lambda *a, **kw: _FakeResp(200, body))
        with pytest.raises(CollectionTooBigToFilterError) as e:
            collection_resolver.resolve_collection("col_big")
        assert e.value.code == 400
        assert e.value.error_code == "collection_too_big_to_filter"
        assert f"{count:,}" in str(e.value)
        if etype == "authors":
            assert "use the Country or Institution filter" in str(e.value)

    @pytest.mark.parametrize("etype, count", [("authors", 100_000), ("sources", 300_000)])
    def test_at_the_live_limit_filters(self, monkeypatch, etype, count):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        ids = [f"X{i}" for i in range(count)]
        monkeypatch.setattr(
            collection_resolver.requests, "get",
            lambda *a, **kw: _FakeResp(200, _member_ids_body(etype, ids)),
        )
        assert collection_resolver.resolve_collection("col_edge") == (etype, ids)

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

    @pytest.mark.parametrize("value", ["col_deleted", "!col_deleted"])
    def test_unreadable_collection_raises_positive_and_negated(self, monkeypatch, value):
        monkeypatch.setattr(collection_resolver, "resolve_collection", _not_found)
        f = CollectionField(entity_type="works")
        f.value = value
        with pytest.raises(CollectionNotFoundError):
            f.build_query()



    def test_invalid_label_id_format_rejected(self, monkeypatch):
        f = CollectionField(entity_type="works")
        f.value = "not-a-collection"
        with pytest.raises(APIQueryParamsError):
            f.build_query()


# ---------- _canonicalize_entity_ids (path-segmented entities, oxjob #396) ----------

class TestCanonicalizePathSegments:
    """Path-segmented entities index `id` with their API path segment
    (`https://openalex.org/countries/US`); users-api stores bare codes, so the
    canonicalizer must insert the segment or the terms clause matches nothing."""

    def _terms_ids(self, entity_type, stored_ids, monkeypatch):
        monkeypatch.setattr(collection_resolver, "resolve_collection",
                            lambda lid: (entity_type, stored_ids))
        f = CollectionField(entity_type=entity_type)
        f.value = "col_abc"
        return f.build_query().to_dict()["terms"]["id"]

    def test_countries_bare_codes_get_segment(self, monkeypatch):
        assert self._terms_ids("countries", ["US", "FR"], monkeypatch) == [
            "https://openalex.org/countries/US",
            "https://openalex.org/countries/FR",
        ]

    def test_sdgs_bare_digits_get_segment(self, monkeypatch):
        assert self._terms_ids("sdgs", ["1", "13"], monkeypatch) == [
            "https://openalex.org/sdgs/1",
            "https://openalex.org/sdgs/13",
        ]

    def test_keywords_slugs_get_segment(self, monkeypatch):
        assert self._terms_ids("keywords", ["computer-science"], monkeypatch) == [
            "https://openalex.org/keywords/computer-science",
        ]

    def test_work_types_segment_is_types(self, monkeypatch):
        # The one name/path mismatch: entity_type `work-types`, path `types/`.
        assert self._terms_ids("work-types", ["article", "book"], monkeypatch) == [
            "https://openalex.org/types/article",
            "https://openalex.org/types/book",
        ]

    def test_awards_native_prefix_no_segment(self, monkeypatch):
        assert self._terms_ids("awards", ["G6558272803"], monkeypatch) == [
            "https://openalex.org/G6558272803",
        ]

    def test_already_segmented_stored_id_not_doubled(self, monkeypatch):
        assert self._terms_ids("countries", ["countries/US"], monkeypatch) == [
            "https://openalex.org/countries/US",
        ]

    def test_off_case_codes_fixed_at_read_time(self, monkeypatch):
        # users-api's lenient gate can store `us` / `q15` / `Article`; the ES
        # id is case-sensitive, so canonicalization fixes case per vocab.
        assert self._terms_ids("countries", ["us"], monkeypatch) == [
            "https://openalex.org/countries/US",
        ]
        assert self._terms_ids("continents", ["q15"], monkeypatch) == [
            "https://openalex.org/continents/Q15",
        ]
        assert self._terms_ids("work-types", ["Article"], monkeypatch) == [
            "https://openalex.org/types/article",
        ]

    def test_full_url_passthrough_for_segmented_type(self, monkeypatch):
        assert self._terms_ids(
            "sdgs", ["https://openalex.org/sdgs/3"], monkeypatch
        ) == ["https://openalex.org/sdgs/3"]

    def test_every_registered_collection_field_has_known_segment_or_native(self):
        """Guard: any endpoint registering a CollectionField must have its
        entity_type either in the segment map or be a known native
        letter-prefixed type — a new path-segmented registration that forgets
        the map entry silently matches nothing."""
        import importlib
        from core.fields import ID_PATH_SEGMENT_BY_ENTITY_TYPE
        from core.properties import ENTITY_FIELDS_MODULES

        native = {"works", "authors", "sources", "institutions", "concepts",
                  "funders", "publishers", "topics", "awards",
                  "locations"}  # verbatim namespaced ids, no prefix (#1524)
        registered = set()
        for entity_type, module_name in ENTITY_FIELDS_MODULES.items():
            mod = importlib.import_module(module_name)
            for f in getattr(mod, "fields", []):
                if isinstance(f, CollectionField):
                    registered.add(f.entity_type)
        assert registered, "no CollectionFields found at all — import wiring broken?"
        unknown = registered - native - set(ID_PATH_SEGMENT_BY_ENTITY_TYPE)
        assert not unknown, (
            f"CollectionField registered for {sorted(unknown)} but they're neither "
            f"known-native nor in ID_PATH_SEGMENT_BY_ENTITY_TYPE"
        )


class TestLocationsCollections:
    """Collections of locations (oxjob #1524): the ES `id` is the namespaced id itself."""

    IDS = ["doi:10.7717/peerj.4375", "pmh:oai:arXiv.org:cond-mat/0404022"]

    def test_location_ids_kept_verbatim(self):
        from core.fields import _canonicalize_entity_ids
        assert _canonicalize_entity_ids(self.IDS, "locations") == self.IDS

    def test_locations_endpoint_takes_collection_filter(self, monkeypatch):
        from locations.fields import fields_dict as locations_fields_dict
        monkeypatch.setattr("core.filter.resolve_collection", lambda lid: ("locations", self.IDS))
        s, remaining = _apply_collection_filters(
            locations_fields_dict, [{"collection": "col_Loc"}], Search(),
        )
        assert remaining == []
        assert {"terms": {"id": self.IDS}} in s.to_dict()["query"]["bool"]["filter"]

    def test_works_collection_on_locations_rejected(self, monkeypatch):
        from locations.fields import fields_dict as locations_fields_dict
        monkeypatch.setattr("core.filter.resolve_collection", lambda lid: ("works", ["W1"]))
        with pytest.raises(APIQueryParamsError) as exc:
            _apply_collection_filters(locations_fields_dict, [{"collection": "col_W"}], Search())
        assert "/locations" in str(exc.value)


class TestCollectionUrlIdsInQuery:
    """A collection's URL `id` works wherever `col_x` does (oxjob #1524)."""

    @pytest.mark.parametrize("raw,want", [
        ("filter=collection:https://openalex.org/collections/col_ab1", "filter=collection:col_ab1"),
        ("filter=collection:!https://openalex.org/collections/col_ab1", "filter=collection:!col_ab1"),
        ("filter=collection:https%3A%2F%2Fopenalex.org%2Fcollections%2Fcol_ab1", "filter=collection:col_ab1"),
        ("filter=authorships.author.id:openalex.org/collections/col_ab1", "filter=authorships.author.id:col_ab1"),
        ("filter=collection:HTTPS://OpenAlex.org/collections/col_ab1&per_page=5", "filter=collection:col_ab1&per_page=5"),
        ("filter=collection:col_ab1", "filter=collection:col_ab1"),
        ("search=collections", "search=collections"),
        ("filter=x:https://openalex.org/collections/other", "filter=x:https://openalex.org/collections/other"),
    ])
    def test_rewrite(self, raw, want):
        assert collection_resolver.short_collection_ids_in_query(raw) == want

    def test_middleware_rewrites_query_string(self):
        seen = {}

        def app(environ, start_response):
            seen["qs"] = environ["QUERY_STRING"]
            return []

        mw = collection_resolver.CollectionUrlIdsInQuery(app)
        mw({"QUERY_STRING": "filter=collection:https://openalex.org/collections/col_ab1"}, None)
        assert seen["qs"] == "filter=collection:col_ab1"


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


# ---------- request-wide caps (oxjob #646 security review H1) ----------

class TestRequestWideCaps:
    def _app(self):
        from flask import Flask
        return Flask(__name__)

    def _fake_users_api(self, monkeypatch, calls, n_ids=3):
        monkeypatch.setattr(settings, "USERS_API_URL", "http://users-api.test")
        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append(url)
            return _FakeResp(200, _member_ids_body("works", [f"W{i}" for i in range(n_ids)]))
        monkeypatch.setattr(collection_resolver.requests, "get", fake_get)

    def test_repeated_collection_resolves_once_per_request(self, monkeypatch):
        calls = []
        self._fake_users_api(monkeypatch, calls)
        with self._app().test_request_context("/works"):
            for _ in range(10):
                collection_resolver.resolve_collection("col_same")
        assert len(calls) == 1

    def test_distinct_collection_cap(self, monkeypatch):
        calls = []
        self._fake_users_api(monkeypatch, calls)
        with self._app().test_request_context("/works"):
            for i in range(collection_resolver.MAX_COLLECTIONS_PER_REQUEST):
                collection_resolver.resolve_collection(f"col_{i}")
            with pytest.raises(APIQueryParamsError):
                collection_resolver.resolve_collection("col_onemore")
        assert len(calls) == collection_resolver.MAX_COLLECTIONS_PER_REQUEST

    def test_request_wide_id_budget(self, monkeypatch):
        calls = []
        # Three collections of 120,000 each pass the 300,000 budget on the third.
        self._fake_users_api(monkeypatch, calls, n_ids=120_000)
        with self._app().test_request_context("/works"):
            collection_resolver.resolve_collection("col_a")
            collection_resolver.resolve_collection("col_b")
            with pytest.raises(APIQueryParamsError):
                collection_resolver.resolve_collection("col_c")

    def test_reference_count_cap(self):
        collection_resolver.check_collection_reference_count(5)
        with pytest.raises(APIQueryParamsError):
            collection_resolver.check_collection_reference_count(6)


# ---------- chunked terms (oxjob #1527) ----------

class TestChunkedTerms:
    """Past 60,000 IDs a collection filter ORs several `terms` clauses: one clause takes
    at most 65,536 values (index.max_terms_count)."""

    def test_any_of_terms_one_clause_when_it_fits(self):
        from core.fields import any_of_terms
        q = any_of_terms(lambda c: Q("terms", id=c), ["a", "b"]).to_dict()
        assert q == {"terms": {"id": ["a", "b"]}}

    def test_any_of_terms_splits_at_60000(self):
        from core.fields import TERMS_CHUNK, any_of_terms
        ids = [f"x{i}" for i in range(2 * TERMS_CHUNK + 1)]
        q = any_of_terms(lambda c: Q("terms", id=c), ids).to_dict()
        clauses = q["bool"]["should"]
        assert q["bool"]["minimum_should_match"] == 1
        assert [len(c["terms"]["id"]) for c in clauses] == [TERMS_CHUNK, TERMS_CHUNK, 1]
        assert [i for c in clauses for i in c["terms"]["id"]] == ids

    def test_same_type_collection_of_130000_ors_three_clauses(self, monkeypatch):
        ids = [f"S{i}" for i in range(1, 130_001)]
        monkeypatch.setattr(
            collection_resolver, "resolve_collection", lambda cid: ("sources", ids),
        )
        field = CollectionField(entity_type="sources")
        field.value = "col_big"
        q = field.build_query().to_dict()
        clauses = q["bool"]["should"]
        assert [len(c["terms"]["id"]) for c in clauses] == [60_000, 60_000, 10_000]
        assert clauses[0]["terms"]["id"][0] == "https://openalex.org/S1"
        field.value = "!col_big"
        # NOT (a OR b OR c): elasticsearch_dsl writes it as must_not [a, b, c].
        negated = field.build_query().to_dict()
        assert [len(c["terms"]["id"]) for c in negated["bool"]["must_not"]] == [60_000, 60_000, 10_000]


def test_openalex_id_terms_fast_path_and_fallback():
    # Canonical short IDs take the fast path; anything else is still normalized.
    from core.fields import OpenAlexIDField
    field = OpenAlexIDField(param="primary_location.source.id", entity_type="sources")
    q = field.build_terms_query(["S11", "s22", "https://openalex.org/S333"]).to_dict()
    (values,) = q["terms"].values()
    assert values == ["https://openalex.org/S11", "https://openalex.org/S22", "https://openalex.org/S333"]
