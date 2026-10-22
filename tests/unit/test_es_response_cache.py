"""core/es_response_cache.py (oxjob #1682): admission on the second ask, shadow vs on, what is never stored."""
import pytest
from elasticsearch_dsl import Q, Search

import settings
from core import es_response_cache as rc
from core.sort import sort_with_sample


class FakeRedis:
    """Just the commands the cache uses: GET, STRLEN, SET (ex, nx), HINCRBY, EXPIRE, and pipelines of them."""

    def __init__(self, broken=False):
        self.kv, self.hashes, self.broken = {}, {}, broken

    def _check(self):
        if self.broken:
            raise ConnectionError("down")

    def get(self, key):
        self._check()
        return self.kv.get(key)

    def strlen(self, key):
        self._check()
        return len(self.kv.get(key, b""))

    def set(self, key, val, ex=None, nx=False):
        self._check()
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    def hincrby(self, key, field, n):
        h = self.hashes.setdefault(key, {})
        h[field] = h.get(field, 0) + n

    def expire(self, key, ttl):
        pass

    def pipeline(self, transaction=True):
        return FakePipe(self)

    def stats(self):
        out = {}
        for h in self.hashes.values():
            for f, n in h.items():
                out[f] = out.get(f, 0) + n
        return out


class FakePipe:
    def __init__(self, r):
        self.r, self.ops = r, []

    def __getattr__(self, name):
        return lambda *a, **kw: self.ops.append((name, a, kw))

    def execute(self):
        return [getattr(self.r, name)(*a, **kw) for name, a, kw in self.ops]


BODY = {"took": 37, "timed_out": False, "_shards": {"total": 72, "successful": 72, "skipped": 0, "failed": 0},
        "hits": {"total": {"value": 2, "relation": "eq"}, "max_score": 1.0,
                 "hits": [{"_index": "works-v39", "_id": "W1", "_score": 1.0, "_source": {"id": "W1"}},
                          {"_index": "works-v39", "_id": "W2", "_score": 0.5, "_source": {"id": "W2"}}]}}


def search():
    return Search(index="works-v39").query(Q("match", title="kelp")).params(timeout="5s", preference="abc")


@pytest.fixture
def cache(monkeypatch):
    """-> (set mode / ES answer, the fake Redis, list of ES calls)."""
    r, calls, answer = FakeRedis(), [], {"body": BODY}

    def fake_execute(self):
        calls.append(1)
        return self._response_class(self, dict(answer["body"]))

    monkeypatch.setattr(Search, "execute", fake_execute)
    monkeypatch.setattr(rc, "_redis", lambda: r)
    monkeypatch.setattr(rc, "FLUSH_S", 0)
    rc._stats.clear()

    def configure(mode, body=BODY, broken=False):
        monkeypatch.setattr(settings, "ES_RESPONSE_CACHE", mode)
        answer["body"], r.broken = body, broken
    return configure, r, calls


def test_off_never_touches_redis(cache):
    configure, r, calls = cache
    configure("off", broken=True)
    assert rc.execute(search()).took == 37
    assert calls == [1] and r.kv == {}


def test_on_admits_on_second_ask_and_serves_the_third(cache):
    configure, r, calls = cache
    configure("on")
    rc.execute(search())                    # 1st: marker only
    assert list(r.kv.values()) == [rc.MARKER]
    rc.execute(search())                    # 2nd: body stored
    assert list(r.kv.values()) != [rc.MARKER]
    served = rc.execute(search())           # 3rd: from Redis, ES not asked
    assert len(calls) == 2
    assert [h.meta.id for h in served] == ["W1", "W2"]
    assert served.hits.total.value == 2
    assert served.took == 0                 # db_response_time_ms stays truthful
    st = r.stats()
    assert (st["lookups"], st["hits"], st["markers"], st["stored"], st["took_saved_ms"]) == (3, 1, 1, 1, 37)


def test_shadow_counts_would_be_hits_but_always_asks_es(cache):
    configure, r, calls = cache
    configure("shadow")
    for _ in range(4):
        assert rc.execute(search()).took == 37
    assert len(calls) == 4
    assert r.stats()["hits"] == 2


def test_partial_and_failed_responses_are_never_stored(cache):
    configure, r, calls = cache
    for bad in ({**BODY, "timed_out": True},
                {**BODY, "_shards": {"total": 72, "successful": 70, "skipped": 0, "failed": 2}}):
        r.kv.clear()
        configure("on", body=bad)
        for _ in range(3):
            rc.execute(search())
        assert list(r.kv.values()) == [rc.MARKER]
    assert len(calls) == 6 and r.stats()["skip_partial"] == 4


def test_unseeded_random_sample_is_never_cached(cache):
    configure, r, calls = cache
    configure("on")
    s = sort_with_sample(Search(index="works-v39"), None)
    for _ in range(3):
        rc.execute(s)
    assert len(calls) == 3 and r.kv == {}
    assert sort_with_sample(Search(index="works-v39"), "7")._params.get("request_cache") is None


def test_key_ignores_preference_and_timeout_but_not_page_or_index():
    def key(s):
        return rc.key_for(s, s.to_dict())
    base = search()
    assert key(base) == key(base.params(preference="other", timeout="9s"))
    assert key(base[0:25]) != key(base[25:50])
    assert key(base) != key(base.index("works-v40"))
    assert key(base) != key(base.extra(track_total_hits=True))


def test_redis_down_falls_back_to_es(cache):
    configure, r, calls = cache
    configure("on", broken=True)
    assert rc.execute(search()).took == 37
    assert calls == [1]


def test_oversized_bodies_are_skipped(cache, monkeypatch):
    configure, r, calls = cache
    configure("on")
    monkeypatch.setattr(settings, "ES_RESPONSE_CACHE_MAX_BYTES", 10)
    for _ in range(3):
        rc.execute(search())
    assert len(calls) == 3 and r.stats()["skip_big"] == 2
