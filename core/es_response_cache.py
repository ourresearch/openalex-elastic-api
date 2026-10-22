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

Admission: a response is stored only the second time its key is asked for within the TTL (the first time
leaves a tiny marker), so one-off pages cost Redis neither space nor bandwidth.
Never stored: timed-out or partial responses (the 5 s soft timeout returns partial hits), shard failures,
unseeded random samples (`random_score: {}` is the same body every time), bodies over the size cap.
A served hit reports took = 0 (meta.db_response_time_ms), so the proxy's ES-time sampling stays true.

Counters per UTC hour, hash esrc:stats:YYYYmmddHH (HGETALL): lookups, hits (shadow: would-be hits),
markers, stored, stored_bytes, took_saved_ms, skip_partial, skip_random, skip_big, errors.
Redis failures never fail a request: the search just goes to ES.
"""
import datetime
import hashlib
import json
import zlib

import settings

PREFIX = "esrc:v1:"
STATS_PREFIX = "esrc:stats:"
STATS_TTL_S = 14 * 24 * 3600
MARKER = b"1"


def mode():
    return settings.ES_RESPONSE_CACHE if settings.ES_RESPONSE_CACHE in ("shadow", "on") else "off"


def _redis():
    from extensions import cache
    return cache.cache._write_client


def key_for(s):
    """The executed Search (already sliced, so from/size are in the body) -> Redis key."""
    params = {k: v for k, v in (s._params or {}).items() if k not in ("preference", "timeout", "request_timeout")}
    raw = json.dumps([str(s._using), s._index, s.to_dict(), params], sort_keys=True, default=str)
    return PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:40]


def _unseeded_random(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "random_score" and not (isinstance(v, dict) and "seed" in v):
                return True
            if _unseeded_random(v):
                return True
    elif isinstance(node, list):
        return any(_unseeded_random(v) for v in node)
    return False


def _count(**fields):
    try:
        r = _redis()
        key = STATS_PREFIX + datetime.datetime.utcnow().strftime("%Y%m%d%H")
        pipe = r.pipeline()
        for f, n in fields.items():
            pipe.hincrby(key, f, int(n))
        pipe.expire(key, STATS_TTL_S)
        pipe.execute()
    except Exception:
        pass


def _storable(body):
    """None if the raw ES response may be stored, else the counter to bump."""
    if body.get("timed_out"):
        return "skip_partial"
    shards = body.get("_shards") or {}
    if shards.get("failed") or (shards.get("successful", 0) < shards.get("total", 0)):
        return "skip_partial"
    return None


def execute(s, run):
    """`s` is the Search about to run; `run()` runs it (and raises as before). Returns its Response."""
    m = mode()
    if m == "off":
        return run()
    try:
        if _unseeded_random(s.to_dict()):
            _count(skip_random=1)
            return run()
        key = key_for(s)
        r = _redis()
        val = r.get(key)
    except Exception:
        _count(errors=1)
        return run()

    if val is not None and val != MARKER and m == "on":
        try:
            body = json.loads(zlib.decompress(val))
            took = body.get("took") or 0
            body["took"] = 0
            response = s._response_class(s, body)
            _count(lookups=1, hits=1, took_saved_ms=took)
            return response
        except Exception:
            _count(errors=1)
            val = None

    response = run()
    try:
        ttl = int(settings.ES_RESPONSE_CACHE_SECONDS)
        if val is None:
            r.set(key, MARKER, ex=ttl, nx=True)
            _count(lookups=1, markers=1)
        elif val == MARKER:
            body = response.to_dict()
            skip = _storable(body)
            if skip:
                _count(lookups=1, **{skip: 1})
            else:
                blob = zlib.compress(json.dumps(body, separators=(",", ":")).encode(), 1)
                if len(blob) > settings.ES_RESPONSE_CACHE_MAX_BYTES:
                    _count(lookups=1, skip_big=1)
                else:
                    r.set(key, blob, ex=ttl)
                    _count(lookups=1, stored=1, stored_bytes=len(blob))
        else:  # shadow: a stored body was there; `on` would have served it
            _count(lookups=1, hits=1, took_saved_ms=getattr(response, "took", 0) or 0)
    except Exception:
        _count(errors=1)
    return response
