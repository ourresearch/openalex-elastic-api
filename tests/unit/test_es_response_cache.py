"""core/es_response_cache.py (oxjob #1682): admission on the second ask, shadow vs on, what is never stored."""
from elasticsearch_dsl import Q, Search

import settings
from core import es_response_cache as rc


class FakePipe:
    def __init__(self, r):
        self.r = r

    def hincrby(self, key, field, n):
        h = self.r.hashes.setdefault(key, {})
        h[field] = h.get(field, 0) + n

    def expire(self, key, ttl):
        pass

    def execute(self):
        pass


class FakeRedis:
    def __init__(self, broken=False):
        self.kv, self.hashes, self.broken = {}, {}, broken

    def get(self, key):
        if self.broken:
            raise ConnectionError("down")
        return self.kv.get(key)

    def set(self, key, val, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = val
        return True

    def pipeline(self):
        return FakePipe(self)

    def stats(self):
        out = {}
        for h in self.hashes.values():
            for f, n in h.items():
                out[f] = out.get(f, 0) + n
        return out


BODY = {"took": 37, "timed_out": False, "_shards": {"total": 72, "successful": 72, "skipped": 0, "failed": 0},
        "hits": {"total": {"value": 2, "relation": "eq"}, "max_score": 1.0,
                 "hits": [{"_index": "works-v39", "_id": "W1", "_score": 1.0, "_source": {"id": "W1"}},
                          {"_index": "works-v39", "_id": "W2", "_score": 0.5, "_source": {"id": "W2"}}]}}


def search(**kw):
    s = Search(index="works-v39").query(Q("match", title="kelp")).params(timeout="5s", preference="abc")
    return s.extra(**kw) if kw else s


def runner(s, body=BODY):
    calls = []

    def run():
        calls.append(1)
        return s._response_class(s, dict(body))
    return run, calls


def setup(monkeypatch, mode, broken=False):
    r = FakeRedis(broken)
    monkeypatch.setattr(settings, "ES_RESPONSE_CACHE", mode)
    monkeypatch.setattr(rc, "_redis", lambda: r)
    return r


def test_off_never_touches_redis(monkeypatch):
    r = setup(monkeypatch, "off", broken=True)
    s = search()
    run, calls = runner(s)
    assert rc.execute(s, run).took == 37
    assert calls == [1] and r.kv == {}


def test_on_admits_on_second_ask_and_serves_the_third(monkeypatch):
    r = setup(monkeypatch, "on")
    s = search()
    run, calls = runner(s)
    rc.execute(s, run)                      # 1st: marker only
    assert list(r.kv.values()) == [rc.MARKER]
    rc.execute(s, run)                      # 2nd: body stored
    assert list(r.kv.values()) != [rc.MARKER]
    served = rc.execute(s, run)             # 3rd: from Redis, ES not asked
    assert len(calls) == 2
    assert [h.meta.id for h in served] == ["W1", "W2"]
    assert served.hits.total.value == 2
    assert served.took == 0                 # db_response_time_ms stays truthful
    st = r.stats()
    assert st["hits"] == 1 and st["markers"] == 1 and st["stored"] == 1 and st["took_saved_ms"] == 37


def test_shadow_counts_would_be_hits_but_always_asks_es(monkeypatch):
    r = setup(monkeypatch, "shadow")
    s = search()
    run, calls = runner(s)
    for _ in range(4):
        assert rc.execute(s, run).took == 37
    assert len(calls) == 4
    assert r.stats()["hits"] == 2


def test_partial_and_failed_responses_are_never_stored(monkeypatch):
    for bad in ({**BODY, "timed_out": True},
                {**BODY, "_shards": {"total": 72, "successful": 70, "skipped": 0, "failed": 2}}):
        r = setup(monkeypatch, "on")
        s = search()
        run, calls = runner(s, bad)
        for _ in range(3):
            rc.execute(s, run)
        assert len(calls) == 3
        assert list(r.kv.values()) == [rc.MARKER]
        assert r.stats()["skip_partial"] == 2


def test_unseeded_random_sample_is_never_cached(monkeypatch):
    r = setup(monkeypatch, "on")
    s = Search(index="works-v39").query(Q("function_score", functions=[{"random_score": {}}]))
    run, calls = runner(s)
    for _ in range(3):
        rc.execute(s, run)
    assert len(calls) == 3 and r.kv == {}
    seeded = Search(index="works-v39").query(
        Q("function_score", functions=[{"random_score": {"seed": 7, "field": "_seq_no"}}]))
    assert not rc._unseeded_random(seeded.to_dict())


def test_key_ignores_preference_and_timeout_but_not_page_or_index():
    base = search()
    assert rc.key_for(base) == rc.key_for(base.params(preference="other", timeout="9s"))
    assert rc.key_for(base[0:25]) != rc.key_for(base[25:50])
    assert rc.key_for(base) != rc.key_for(base.index("works-v40"))
    assert rc.key_for(base) != rc.key_for(base.extra(track_total_hits=True))


def test_redis_down_falls_back_to_es(monkeypatch):
    setup(monkeypatch, "on", broken=True)
    s = search()
    run, calls = runner(s)
    assert rc.execute(s, run).took == 37
    assert calls == [1]


def test_oversized_bodies_are_skipped(monkeypatch):
    r = setup(monkeypatch, "on")
    monkeypatch.setattr(settings, "ES_RESPONSE_CACHE_MAX_BYTES", 10)
    s = search()
    run, calls = runner(s)
    for _ in range(3):
        rc.execute(s, run)
    assert len(calls) == 3 and r.stats()["skip_big"] == 2
