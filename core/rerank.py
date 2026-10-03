"""rerank=true on works searches (oxjob #1521, DESIGN § 3-5).

Jev (TypeSafe's decision model) reorders the top RERANK_WINDOW (100) results of a
relevance-sorted works search: one request carrying the query and, per candidate,
title, venue, year and type, with one yes/no question per candidate; the 100 are
sorted by Jev's probability of yes. Everything after position 100 keeps the normal
order, so rerank never adds, removes or repeats a result and meta.count is unchanged.

- Pages: positions are computed as usual. A page inside the first 100 reads the
  reranked order; a page past 100 is the normal page; a page that straddles 100 takes
  the rest of the reranked 100 and continues with normal position 101.
- Cursor: the walk returns the same works as without rerank. The first 100 come in
  reranked order (per_page at a time), then the cursor hands over to the normal
  order at position 101.
- Jev is not deterministic, so the order is computed once and cached (Redis, 24 h);
  every page and cursor step reads the cached order.
- Safety: a hard deadline on the Jev call (RERANK_TIMEOUT_S) and a per-process
  circuit breaker. On timeout, error or an open breaker the normal order is
  returned with meta.reranked = false. The Jev call is direct (not through the Jev
  broker): the broker shares out 380 of the account's 400 req/s, and the API's
  rerank traffic sits in the 20 req/s it keeps back.
"""
import base64
import datetime
import hashlib
import json
import logging
import threading
import time

import requests
from elasticsearch_dsl.response import Response

import settings
from core.cursor import encode_cursor
from core.exceptions import APIQueryParamsError

CACHE_PREFIX = "rerank:v1:"
CURSOR_PREFIX = "rr."
LIGHT_SOURCE = ["id", "display_name", "publication_year", "type", "primary_location.source.display_name"]
INSTRUCTIONS = (
    "A researcher typed the search query shown in state into an academic search engine. "
    "Is candidate {i} a relevant result, i.e. a work this researcher would want to see near the top "
    "of the results because it is directly about what the query asks for? "
    "Answer yes only if the work's own subject matches the query's intent; "
    "answer no if it merely shares a few words or a broad topic with the query."
)
# Args that don't change which works match or their normal order.
NOT_IN_CACHE_KEY = {
    "page", "per_page", "per-page", "cursor", "select", "api_key", "api-key", "mailto", "rerank",
    "format", "bypass_cache", "warm",
}


def rerank_requested(request):
    value = request.args.get("rerank")
    if value is None:
        return False
    if value not in ("true", "false"):
        raise APIQueryParamsError("rerank must be true or false.")
    return value == "true"


def query_text(params):
    """The text Jev judges against: the search param(s) and any *.search filter values."""
    parts = []
    if params.get("searches"):
        parts += [s["search"] for s in params["searches"] if s.get("search_type") != "semantic"]
    elif params.get("search") and params.get("search_type") != "semantic":
        parts.append(params["search"])
    for f in params.get("filters") or []:
        for k, v in f.items():
            if (k.endswith(".search") or k.endswith(".search.exact")) and k != "semantic.search" and v:
                parts.append(str(v).lstrip("!"))
    return " ; ".join(p.strip() for p in parts if p and p.strip() and p != '""')


def oqo_query_text(filter_rows):
    """The search text of an OQO (the OQL door): every non-negated *.search leaf's value."""
    parts = []

    def walk(node):
        if hasattr(node, "to_dict"):
            node = node.to_dict()
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            col = node.get("column_id")
            if isinstance(col, str):
                if (col.endswith(".search") or col.endswith(".search.exact")) and col != "semantic.search" \
                        and not node.get("is_negated") and node.get("value") not in (None, ""):
                    parts.append(str(node["value"]))
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v)

    walk(filter_rows)
    return " ; ".join(parts)


def validate(params, index_name, query=None):
    """400 for every combination rerank can't honor; never silently ignored."""
    if not index_name.lower().startswith("works"):
        raise APIQueryParamsError("rerank is only supported on /works.")
    if params.get("search_type") == "semantic":
        raise APIQueryParamsError("rerank=true can't be combined with search.semantic, which already ranks by meaning.")
    if params.get("group_by") or params.get("group_bys"):
        raise APIQueryParamsError("rerank=true can't be combined with group_by: rerank orders results, and group_by returns counts.")
    if params.get("sample"):
        raise APIQueryParamsError("rerank=true can't be combined with sample, which returns results in random order.")
    if params.get("sort") and params["sort"] != {"relevance_score": "desc"}:
        raise APIQueryParamsError("rerank=true reorders results by relevance, so it can't be combined with sort (other than sort=relevance_score:desc).")
    if not (query if query is not None else query_text(params)):
        raise APIQueryParamsError("rerank=true needs a search (search=, search.title_abstract_keywords=, or a .search filter).")


logger = logging.getLogger(__name__)
STATS_PREFIX = "rerank:stats:"
STATS_TTL_S = 45 * 24 * 3600


def record(outcome, ms=None):
    """Count one rerank outcome in Redis, per UTC day (hash rerank:stats:YYYY-MM-DD):
    computed / cache_hit / timeout / http_<code> / error / breaker_open / no_key / no_results,
    plus computed_ms_sum and latency buckets ms_lt300 / ms_lt600 / ms_ge600 for Jev calls that answered.
    Read with HGETALL. Failures here never affect the request."""
    try:
        r = _cache().cache._write_client
        key = STATS_PREFIX + datetime.datetime.utcnow().strftime("%Y-%m-%d")
        pipe = r.pipeline()
        pipe.hincrby(key, outcome, 1)
        if ms is not None:
            pipe.hincrby(key, "computed_ms_sum", int(ms))
            pipe.hincrby(key, "ms_lt300" if ms < 300 else "ms_lt600" if ms < 600 else "ms_ge600", 1)
        pipe.expire(key, STATS_TTL_S)
        pipe.execute()
    except Exception:
        pass
    if outcome not in ("computed", "cache_hit", "no_results"):
        logger.warning("rerank fallback: %s", outcome)


# ---------- circuit breaker (per gunicorn worker process) ----------

class Breaker:
    def __init__(self, failures=5, window_s=30, open_s=60):
        self.failures, self.window_s, self.open_s = failures, window_s, open_s
        self._fails = []
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow(self):
        return time.monotonic() >= self._open_until

    def record(self, ok):
        now = time.monotonic()
        with self._lock:
            if ok:
                self._fails = []
                return
            self._fails = [t for t in self._fails if now - t < self.window_s] + [now]
            if len(self._fails) >= self.failures:
                self._open_until = now + self.open_s
                self._fails = []


breaker = Breaker()
_session = requests.Session()


def jev_probabilities(query, cands):
    """p(yes) per candidate, or None on any failure (timeout, HTTP error, missing answer)."""
    if not getattr(settings, "TYPESAFE_API_KEY", None):
        record("no_key")
        return None
    if not breaker.allow():
        record("breaker_open")
        return None
    state = "SEARCH QUERY: " + query + "\n\nCANDIDATES:\n\n" + "\n\n".join(
        f"[{i}] Title: {c['title']}\nVenue: {c['venue']} ({c['year']}, {c['type']})" for i, c in enumerate(cands)
    )
    body = {
        "model": getattr(settings, "JEV_MODEL", "jev-1.13.0"),
        "state": state,
        "questions": {f"n{i}": {"type": "noul", "instructions": INSTRUCTIONS.format(i=i)} for i in range(len(cands))},
    }
    t0 = time.monotonic()
    try:
        r = _session.post(
            getattr(settings, "JEV_URL", "https://api.typesafe.ai/v1/systemone"), json=body,
            headers={"Authorization": f"Bearer {settings.TYPESAFE_API_KEY}"},
            timeout=(0.25, getattr(settings, "RERANK_TIMEOUT_S", 0.6)),
        )
        if r.status_code != 200:
            breaker.record(False)
            record(f"http_{r.status_code}")
            return None
        answers = r.json().get("answers") or {}
        p = [(answers.get(f"n{i}") or {}).get("noul") for i in range(len(cands))]
        if any(x is None for x in p):
            raise ValueError("Jev answer missing")
    except requests.exceptions.Timeout:
        breaker.record(False)
        record("timeout")
        return None
    except Exception:
        breaker.record(False)
        record("error")
        return None
    breaker.record(True)
    record("computed", (time.monotonic() - t0) * 1000)
    return [float(x) for x in p]


def _window(search, start, size):
    """from/size set explicitly: the Search arrives with extra(size=per_page), and
    slicing on top of that differs between elasticsearch-dsl versions."""
    return search.extra(**{"from": start, "size": size})


# ---------- cached order ----------

def cache_key(request, index_name, extra=None):
    """extra: what else defines the query (the OQO for the OQL door, whose POST body isn't in the args).
    Its view fields (page, per_page, cursor, select) are dropped like the URL's: every page shares one order."""
    if isinstance(extra, dict):
        extra = {k: v for k, v in extra.items() if k not in ("page", "per_page", "cursor", "select")}
    args = sorted((k, v) for k, v in request.args.items(multi=True) if k not in NOT_IN_CACHE_KEY)
    raw = json.dumps([index_name, settings.JEV_MODEL, settings.RERANK_WINDOW, settings.CITATION_SCALING,
                      settings.SEARCH_KEYWORDS, args, extra], sort_keys=True, default=str)
    return CACHE_PREFIX + hashlib.sha1(raw.encode()).hexdigest()


def _cache():
    from extensions import cache
    return cache


def cache_get(key):
    try:
        return _cache().get(key)
    except Exception:
        return None


def cache_set(key, entry):
    try:
        _cache().set(key, entry, timeout=settings.RERANK_CACHE_SECONDS)
    except Exception:
        pass


def compute_order(base_search, params, key, query=None):
    """Fetch the normal top RERANK_WINDOW (titles only), ask Jev, cache the order.
    Returns the cache entry, or None if Jev didn't answer in time."""
    window = settings.RERANK_WINDOW
    resp = _window(base_search.source(LIGHT_SOURCE), 0, window).execute()
    raw = resp.to_dict()["hits"]["hits"]
    cands = []
    for h in raw:
        src = h.get("_source") or {}
        venue = (((src.get("primary_location") or {}).get("source")) or {}).get("display_name") or ""
        cands.append({"id": src.get("id"), "title": src.get("display_name") or "", "venue": venue,
                      "year": src.get("publication_year"), "type": src.get("type")})
    if not cands:
        record("no_results")
    entry = {"ids": [], "scores": [], "count": resp.hits.total.value,
             "after": raw[-1].get("sort") if len(raw) == window else None}
    if cands:
        p = jev_probabilities(query if query is not None else query_text(params), cands)
        if p is None:
            return None
        order = sorted(range(len(cands)), key=lambda i: (-p[i], i))
        entry["ids"] = [cands[i]["id"] for i in order]
        entry["scores"] = [round(p[i], 4) for i in order]
    cache_set(key, entry)
    return entry


# ---------- cursor ----------

def encode_rerank_cursor(offset, key):
    """A cursor inside the reranked window: "rr." + base64 {offset, cache key}."""
    return CURSOR_PREFIX + base64.urlsafe_b64encode(json.dumps({"o": offset, "k": key}).encode()).decode()


def decode_rerank_cursor(cursor):
    if not cursor or not cursor.startswith(CURSOR_PREFIX):
        return None
    try:
        rec = json.loads(base64.urlsafe_b64decode(cursor[len(CURSOR_PREFIX):].encode()))
        if not str(rec["k"]).startswith(CACHE_PREFIX):
            raise ValueError
        return {"o": int(rec["o"]), "k": str(rec["k"])}
    except Exception:
        raise APIQueryParamsError("Cursor value is invalid.")


def is_rerank_cursor(cursor):
    return bool(cursor) and cursor.startswith(CURSOR_PREFIX)


# ---------- the reranked page ----------

def reranked_response(request, params, index_name, build_search, query=None, key_extra=None):
    """The reranked page as (response, meta_overrides), or None to run the normal
    search instead (page past the window, a normal cursor, or Jev unavailable).

    build_search(page_params) -> the normal Search for these params, without slicing.
    """
    window = settings.RERANK_WINDOW
    per_page = params["per_page"]
    cursor = params.get("cursor")
    rr = decode_rerank_cursor(cursor)
    if cursor and cursor != "*" and rr is None:
        return None  # a normal cursor: the walk is past the reranked window
    start = rr["o"] if rr else (0 if cursor == "*" else (params["page"] - 1) * per_page)
    if start >= window:
        return None

    first_page = dict(params, cursor=None, page=1)
    base = build_search(first_page)
    key = rr["k"] if rr else cache_key(request, index_name, key_extra)
    entry = cache_get(key)
    if entry is not None:
        record("cache_hit")
    else:
        entry = compute_order(base, params, key, query)
    if entry is None:
        if not rr:
            return None
        # Mid-walk, the cached order is gone and Jev didn't answer: continue in the
        # normal order from the same position and hand over to a normal cursor.
        resp = _window(base, start, per_page).execute()
        raw = resp.to_dict()["hits"]["hits"]
        last = raw[-1].get("sort") if len(raw) == per_page else None
        return resp, {"reranked": False, "page": None, "next_cursor": encode_cursor(last) if last else None}

    ids, scores = entry["ids"], entry["scores"]
    n = len(ids)
    end = start + per_page
    head = ids[start:min(end, n)]
    hits = []
    resp = None
    if head:
        resp = _window(base.filter("terms", id=head), 0, len(head)).execute()
        by_id = {h["_source"]["id"]: h for h in resp.to_dict()["hits"]["hits"]}
        score_of = dict(zip(ids, scores))
        for i in head:
            h = by_id.get(i)
            if h is None:
                continue  # left the index since the order was cached
            h["_source"]["rerank_score"] = score_of[i]
            hits.append(h)
    tail = []
    if end > n and n == window:
        tail_resp = _window(base, window, end - window).execute()
        tail = tail_resp.to_dict()["hits"]["hits"]
        resp = resp or tail_resp
    if resp is None:
        resp = _window(base, 0, 0).execute()

    d = resp.to_dict()
    d["hits"]["hits"] = hits + tail
    d["hits"]["total"] = {"value": entry["count"], "relation": "eq"}
    out = Response(base, d)

    meta = {"reranked": True}
    if cursor:
        meta["page"] = None
        if end < n:
            meta["next_cursor"] = encode_rerank_cursor(end, key)
        elif end == n:
            meta["next_cursor"] = encode_cursor(entry["after"]) if entry["after"] else None
        else:
            last = tail[-1].get("sort") if len(tail) == end - window else None
            meta["next_cursor"] = encode_cursor(last) if last else None
    return out, meta
