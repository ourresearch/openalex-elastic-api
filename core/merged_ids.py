"""Merged work, author, source and funder IDs resolve to the surviving record, best effort with no
permanence promise (oxjob #1124; works and the no-promise wording, Jason 2026-10-27, #1037).

A merged-away entity has no doc in its entity index. One ES index per entity holds a doc per loser,
keyed by its full URL: {id, merge_into_id}. `merge-works`, `merge-authors` and `merge-sources` are
written daily by openalex-walden `notebooks/elastic/sync_merged_ids` from the merge ledgers (chains
already followed to a live winner); `merge-funders` by `MergeFunders.ipynb`.

Two callers: the single-record GET answers a loser ID with a 301 to the winner (ids/views.py), and
ID filters also match the winner (core.fields.OpenAlexIDField), so `filter=authorships.author.id:<loser>`
returns the winner's works.
"""
import logging
import re
import threading
import time
from collections import OrderedDict

from elasticsearch_dsl.connections import get_connection

import settings
from core.rerank import Breaker

logger = logging.getLogger(__name__)

MERGE_INDEXES = {"W": "merge-works", "A": "merge-authors", "S": "merge-sources", "F": "merge-funders"}
URL_PREFIX = "https://openalex.org/"

# Longer ID lists are not looked up: saved collections can carry 260K source IDs, built from live IDs.
MAX_LOOKUP_IDS = settings.MAX_IDS_IN_FILTER

_TTL_SECONDS = 3600          # the indexes change once a day
_CACHE_SIZE = 50_000         # shortcut: per-process LRU (workers recycle every ~500 requests); a miss costs one ES lookup
_TIMEOUT_SECONDS = 1         # a lookup is an ids query: milliseconds when ES is healthy

_cache = OrderedDict()       # short id -> (winner short id or None, expires_at)
_lock = threading.Lock()
# fail open: after repeated errors on an index, skip it for a minute and serve IDs as given
_breakers = {index: Breaker(failures=3, window_s=30, open_s=60) for index in MERGE_INDEXES.values()}

_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9])[WASFwasf]\d{2,}(?![0-9])")


def merged_winners(short_ids, connection="default"):
    """{loser: winner} (short IDs) for the given IDs that were merged away.

    Takes canonical short IDs (`A5107411446`). Only work, author, source and funder IDs are looked up;
    IDs that were never merged, or of other types, are absent from the result."""
    now = time.time()
    out, todo = {}, {}
    with _lock:
        for sid in short_ids:
            index = MERGE_INDEXES.get(sid[:1])
            if index is None:
                continue
            hit = _cache.get(sid)
            if hit and hit[1] > now:
                _cache.move_to_end(sid)
                if hit[0]:
                    out[sid] = hit[0]
            elif _breakers[index].allow():
                todo.setdefault(index, set()).add(sid)

    for index, sids in todo.items():
        try:
            res = get_connection(connection).search(
                index=index,
                body={"size": len(sids), "_source": ["merge_into_id"],
                      "query": {"ids": {"values": [URL_PREFIX + s for s in sids]}}},
                request_timeout=_TIMEOUT_SECONDS,
            )
            found = {h["_id"].removeprefix(URL_PREFIX): h["_source"]["merge_into_id"].removeprefix(URL_PREFIX)
                     for h in res["hits"]["hits"]}
        except Exception:
            logger.warning("merged_ids: lookup on %s failed; serving IDs as given", index, exc_info=True)
            _breakers[index].record(False)
            continue
        _breakers[index].record(True)
        with _lock:
            for sid in sids:
                winner = found.get(sid)
                _cache[sid] = (winner, now + _TTL_SECONDS)
                _cache.move_to_end(sid)
                if winner:
                    out[sid] = winner
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return out


def merged_winner(short_id, connection="default"):
    """The winner's short ID if `short_id` was merged away, else None."""
    return merged_winners([short_id], connection).get(short_id)


def with_winners(full_ids):
    """`full_ids` (full-URL OpenAlex IDs) plus the winner of each merged-away one among them.

    The loser stays in the list so a work still stamped with it (until the next nightly re-stamp)
    matches too. Lists over MAX_LOOKUP_IDS come back unchanged."""
    if len(full_ids) > MAX_LOOKUP_IDS:
        return list(full_ids)
    shorts = [v.removeprefix(URL_PREFIX) for v in full_ids]
    winners = merged_winners(shorts)
    extra = [URL_PREFIX + winners[s] for s in shorts if s in winners]
    return list(full_ids) + [w for w in extra if w not in full_ids]


def prefetch(raw_values):
    """Warm the cache with every work / author / source / funder ID in raw filter values, in one lookup per
    index, so a filter that resolves its IDs one by one (AND lists, negated ORs) doesn't make N calls."""
    ids = {m.group(0).upper() for v in raw_values for m in _ID_TOKEN.finditer(v)}
    if len(ids) > 1:
        merged_winners(sorted(ids)[:MAX_LOOKUP_IDS])
