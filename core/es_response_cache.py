"""Serve repeated Elasticsearch searches from Redis (oxjob #1682, lever 14).

Two identical ES requests (same cluster, index and body) return the same answer until the index next
refreshes (hourly), so a repeat within a few minutes can come from Redis instead of 72 shards. The key is
the ES request itself, not the URL: api_key, mailto, parameter order and spelling all collapse to one
entry; a collection filter is already its member IDs in the body, so the key changes when the members do;
an alias swap (works-v39 -> v40) changes the index name. Everything above the ES call (credit checks,
pricing, meta.cost_usd, serialization) still runs on every request; a hit only skips the ES round trip.

Mode, env ES_RESPONSE_CACHE (set it on BOTH Heroku apps; searches go to openalex-search-api):
  off     default: untouched.
  shadow  look up and fill, but always ask ES: counts what `on` would have served.
  on      serve hits.
Store: ES_RESPONSE_CACHE_URL (default: the shared REDISCLOUD_URL), its own client with short timeouts so a
Redis stall can't hold a request. Give it its own Redis: the replay (oxjob #1682) puts its traffic at ~80-150
GB/day compressed, far over Redis Cloud's 400 GB/month on the shared 2.5 GB plan; Heroku Key-Value Store has no
network cap (premium-5: 1 GB, 1,000 connections; we need ~540 = 135 dynos x 4 workers). Set its
maxmemory policy to allkeys-lru (the default, noeviction, would make SETs fail when full).

Admission: a response is stored only the second time its key is asked for within the TTL (the first ask
leaves a 1-byte marker), so one-off pages cost Redis neither space nor bandwidth.
Never stored: timed-out or partial responses (the 5 s soft timeout returns partial hits), shard failures,
searches that opt out with request_cache=False (unseeded random samples, core/sort.py), oversized bodies.
A served hit reports took = 0 (meta.db_response_time_ms), so the proxy's ES-time sampling stays true.

Counters per UTC hour, hash esrc:stats:YYYYmmddHH (HGETALL), buffered per worker and flushed every
FLUSH_S: lookups, hits (shadow: would-be hits), markers, stored, stored_bytes, took_saved_ms, skip_partial,
skip_big, errors. Redis failures never fail a request: the search just goes to ES.
"""
import datetime
import hashlib
import json
import threading
import time
import zlib
from collections import Counter

import settings

PREFIX = "esrc:v1:"
STATS_PREFIX = "esrc:stats:"
STATS_TTL_S = 14 * 24 * 3600
FLUSH_S = 10
MARKER = b"1"

_client = None
_stats = Counter()
_stats_lock = threading.Lock()
_last_flush = time.monotonic()


def _redis():
    global _client
    if _client is None:
        import redis
        url = settings.ES_RESPONSE_CACHE_URL
        kw = {"socket_timeout": 0.25, "socket_connect_timeout": 0.25}
        if url.startswith("rediss://"):
            kw["ssl_cert_reqs"] = None  # Heroku Key-Value Store's TLS certificate is self-signed
        _client = redis.Redis.from_url(url, **kw)
    return _client


def key_for(s, body):
    """The executed Search (already sliced, so from/size are in `body`) -> Redis key."""
    params = {k: v for k, v in s._params.items() if k not in ("preference", "timeout", "request_timeout")}
    raw = json.dumps([str(s._using), s._index, body, params], sort_keys=True, default=str)
    return PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:40]


def _count(stats):
    """Add to this worker's counters; flush them to Redis at most every FLUSH_S."""
    global _last_flush
    with _stats_lock:
        _stats.update(stats)
        if time.monotonic() - _last_flush < FLUSH_S:
            return
        pending = dict(_stats)
        _stats.clear()
        _last_flush = time.monotonic()
    try:
        key = STATS_PREFIX + datetime.datetime.utcnow().strftime("%Y%m%d%H")
        pipe = _redis().pipeline(transaction=False)
        for f, n in pending.items():
            pipe.hincrby(key, f, int(n))
        pipe.expire(key, STATS_TTL_S)
        pipe.execute()
    except Exception:
        pass  # these counts are lost; requests are unaffected


def _partial(body):
    shards = body.get("_shards") or {}
    return bool(body.get("timed_out") or shards.get("failed")
                or shards.get("successful", 0) < shards.get("total", 0))


def execute(s):
    """Run Search `s` (raising as s.execute() would), from Redis when an identical search was stored."""
    mode = settings.ES_RESPONSE_CACHE
    if mode == "off" or s._params.get("request_cache") is False:
        return s.execute()
    ttl = settings.ES_RESPONSE_CACHE_SECONDS
    try:
        key = key_for(s, s.to_dict())
        pipe = _redis().pipeline(transaction=False)
        # shadow only needs to know absent (0) / marker (1) / body (>1), not to download the body
        pipe.strlen(key) if mode == "shadow" else pipe.get(key)
        pipe.set(key, MARKER, ex=ttl, nx=True)  # no-op unless absent
        found, _ = pipe.execute()
    except Exception:
        _count({"errors": 1})
        return s.execute()

    stats = {"lookups": 1}
    if mode == "on" and found and found != MARKER:
        try:
            body = json.loads(zlib.decompress(found))
            stats.update(hits=1, took_saved_ms=body.get("took") or 0)
            body["took"] = 0
            _count(stats)
            return s._response_class(s, body)
        except Exception:
            stats["errors"] = 1
            found = None

    response = s.execute()
    if not found:
        stats["markers"] = 1
    elif found in (MARKER, 1):  # second ask: store the body
        body = response.to_dict()
        blob = None if _partial(body) else zlib.compress(json.dumps(body, separators=(",", ":")).encode(), 1)
        if blob is None:
            stats["skip_partial"] = 1
        elif len(blob) > settings.ES_RESPONSE_CACHE_MAX_BYTES:
            stats["skip_big"] = 1
        else:
            try:
                _redis().set(key, blob, ex=ttl)
                stats.update(stored=1, stored_bytes=len(blob))
            except Exception:
                stats["errors"] = 1
    else:  # shadow, a body is stored: `on` would have served it
        stats.update(hits=1, took_saved_ms=getattr(response, "took", 0) or 0)
    _count(stats)
    return response
