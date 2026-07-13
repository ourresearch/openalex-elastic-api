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
import os
import random
import threading
import time

import psycopg2
from elasticsearch_dsl.utils import AttrDict
from psycopg2 import pool as pg_pool

N_DOC_SHARDS = 8  # lakebase.lakebase_works_docs_{work_id % 8}

# Canary dial — ramp by editing this constant and deploying (see module docstring).
DEFAULT_LOOKUP_PCT = 10

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


def get_work_doc(work_id):
    """work_id (int) -> parsed doc dict, or None if absent."""
    shard = work_id % N_DOC_SHARDS
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
