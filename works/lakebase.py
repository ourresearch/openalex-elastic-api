"""Lakebase-backed single-work lookups (oxjob #576, Phase 2).

Serves GET /works/{id} point lookups from the Lakebase Postgres instance
(`openalex-lookups`) instead of Elasticsearch. The stored doc is the ES
`_source` shape, so it flows through the existing WorksSchema unchanged and
responses stay byte-identical. ES remains the fallback on any miss or error.

Routing: LAKEBASE_URL must be set; then either the canary percentage or a
force signal (`X-Lakebase: 1` header / `?lakebase=1`) sends a request here.

The canary percentage is DEFAULT_LOOKUP_PCT below and is ramped BY DEPLOY
(0 -> 1 -> 10 -> 100), not by config var: Heroku config changes hard-restart
every dyno at once, while deploys roll gently. LAKEBASE_LOOKUP_PCT remains
as an unset-by-default emergency override (e.g. slam to 0 without a deploy).
"""
import json
import logging
import os
import random
import threading
import time

import psycopg2
from elasticsearch_dsl.utils import AttrDict
from psycopg2 import pool as pg_pool

N_DOC_SHARDS = 8  # lakebase.lakebase_works_docs_{work_id % 8}

# Canary dial — ramp by editing this constant and deploying (see module docstring).
DEFAULT_LOOKUP_PCT = 100

_pool = None
_pool_lock = threading.Lock()


def lakebase_enabled():
    return bool(os.getenv("LAKEBASE_URL"))


def lookup_pct():
    override = os.getenv("LAKEBASE_LOOKUP_PCT")
    if override is not None:
        try:
            return float(override)
        except ValueError:
            pass
    return float(DEFAULT_LOOKUP_PCT)


def should_route(request):
    """Decide whether this request goes to Lakebase (canary pct or force flag)."""
    if not lakebase_enabled():
        return False
    if request.headers.get("X-Lakebase") == "1" or request.args.get("lakebase") in ("1", "true"):
        return True
    return random.random() * 100 < lookup_pct()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=int(os.getenv("LAKEBASE_POOL_MAX", "4")),
                    dsn=os.getenv("LAKEBASE_URL"),
                )
    return _pool


def _query_one(sql, params):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        pool.putconn(conn)


# oxjob #2082: fwci, citation_normalized_percentile and cited_by_percentile_year move every night without re-stamping a
# work, so the stored doc keeps the values of its last re-stamp. lakebase.lakebase_work_metrics (one narrow row per work,
# kept to the night's values by walden notebooks/lakebase/BuildLakebaseWorkMetrics) overrides them. On since 7 Nov 2026
# (table synced and granted to this role). On any error the plain doc query answers and the overlay stays off a while.
# Off switch without a deploy: config var LAKEBASE_METRICS_OVERLAY=0.
METRICS_OVERLAY = True
METRICS_RETRY_S = 300
_metrics_off_until = 0.0

_METRICS_COLS = "m.work_id, m.fwci, m.has_cnp, m.cnp_value, m.cnp_top_1, m.cnp_top_10, m.has_pct, m.pct_min, m.pct_max"


def metrics_overlay_on():
    override = os.getenv("LAKEBASE_METRICS_OVERLAY")
    on = override == "1" if override in ("0", "1") else METRICS_OVERLAY
    return on and time.time() >= _metrics_off_until


def apply_metrics(doc, m):
    """Overwrite the doc's three metric fields with the metrics row (work_id, fwci, has_cnp, ...); no row -> unchanged."""
    if m is None or m[0] is None:
        return doc
    _, fwci, has_cnp, cnp_value, top_1, top_10, has_pct, pct_min, pct_max = m
    doc["fwci"] = fwci
    doc["citation_normalized_percentile"] = (
        {"value": cnp_value, "is_in_top_1_percent": top_1, "is_in_top_10_percent": top_10} if has_cnp else None
    )
    doc["cited_by_percentile_year"] = {"min": pct_min, "max": pct_max} if has_pct else None
    return doc


def get_work_doc(work_id):
    """work_id (int) -> parsed doc dict, or None if absent."""
    global _metrics_off_until
    shard = work_id % N_DOC_SHARDS
    if metrics_overlay_on():
        try:
            row = _query_one(
                f"SELECT d.doc, {_METRICS_COLS} FROM lakebase.lakebase_works_docs_{shard} d "
                "LEFT JOIN lakebase.lakebase_work_metrics m ON m.work_id = d.work_id WHERE d.work_id = %s",
                (work_id,),
            )
            return apply_metrics(json.loads(row[0]), row[1:]) if row else None
        except Exception:
            logging.getLogger(__name__).exception("lakebase metrics overlay failed; plain doc for %ss", METRICS_RETRY_S)
            _metrics_off_until = time.time() + METRICS_RETRY_S
    row = _query_one(
        f"SELECT doc FROM lakebase.lakebase_works_docs_{shard} WHERE work_id = %s",
        (work_id,),
    )
    return json.loads(row[0]) if row else None


def get_work_doc_by_ext_id(ext_id):
    """ext_id (DOI/PMID in the URL form the API queries) -> doc dict or None."""
    row = _query_one(
        "SELECT work_id FROM lakebase.lakebase_works_ids WHERE ext_id = %s",
        (ext_id,),
    )
    return get_work_doc(row[0]) if row else None


class LakebaseHit(AttrDict):
    """Wrap a parsed doc in elasticsearch_dsl's AttrDict — the same class ES
    hits use — so WorksSchema sees identical semantics: recursive attribute
    access on nested objects (LocationSchema.get_id does getattr on each
    location), attribute set/del for pre_dump's authorships swap, and a
    `.meta.score` stub (None -> relevance_score dropped, matching
    display_relevance=False)."""

    def __init__(self, doc):
        doc = dict(doc)
        doc["meta"] = {"score": None}
        super().__init__(doc)
