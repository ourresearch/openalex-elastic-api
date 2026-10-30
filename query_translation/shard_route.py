"""Which shard holds a work, so a big id filter asks each shard only for its own ids (oxjob #1930).

A set in parentheses becomes a `terms` filter on work ids. Sent whole, every one of the works index's 72 shards
looks up every id, though each id lives on exactly one of them: ES puts a document on
`floorMod(murmur3(_id), routing_shards) / (routing_shards / shards)` (OperationRouting, default routing by `_id`).
Computing that here and sending each piece only to the shards that hold its ids gives the same answer for 1/72 of
the lookups: the 647,203 works cited by KU's works since 2020, filtered and split by source, 1.4 s routed vs 3.2 s
in 8 unrouted pieces (works-v40, 2026-10-30).

The routing is read from the index's settings and checked against ES itself (a few documents looked up by `id` on
the shard this module names for them); if the check fails nothing is routed, so a wrong guess can only cost speed,
never rows.
"""
import time
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_C1, _C2 = np.uint32(0xcc9e2d51), np.uint32(0x1b873593)
_BATCH = 100_000            # ids hashed at a time (bounds the byte arrays to a few MB)
_CHECK_DOCS = 16
_TTL_S = 60.0               # an alias swap reaches the routing within a minute
_known: Dict[str, Tuple[float, Optional[Tuple[str, int, int]]]] = {}
_checked: Dict[str, bool] = {}


def _rotl(x, r):
    return (x << np.uint32(r)) | (x >> np.uint32(32 - r))


def _mix(k):
    return _rotl(k * _C1, 15) * _C2


def _hash_same_length(group: Sequence[str], length: int) -> Optional[np.ndarray]:
    """ES's Murmur3HashFunction.hash(String) of strings that all have `length` characters: murmur3_x86_32, seed 0,
    over each character as two little-endian bytes. None if any character isn't in the Basic Multilingual Plane."""
    raw = "".join(group).encode("utf-16-le")
    width = 2 * length
    if len(raw) != width * len(group):
        return None
    data = np.frombuffer(raw, dtype=np.uint8).reshape(len(group), width)
    full = width // 4
    h = np.zeros(len(group), dtype=np.uint32)
    with np.errstate(over="ignore"):
        if full:
            blocks = np.ascontiguousarray(data[:, :full * 4]).view("<u4")
            for j in range(full):
                h ^= _mix(blocks[:, j])
                h = _rotl(h, 13) * np.uint32(5) + np.uint32(0xe6546b64)
        if width % 4:   # the 2-byte tail of a string with an odd number of characters
            tail = data[:, full * 4].astype(np.uint32) | (data[:, full * 4 + 1].astype(np.uint32) << np.uint32(8))
            h ^= _mix(tail)
        h ^= np.uint32(width)
        h ^= h >> np.uint32(16)
        h *= np.uint32(0x85ebca6b)
        h ^= h >> np.uint32(13)
        h *= np.uint32(0xc2b2ae35)
        h ^= h >> np.uint32(16)
    return h.view(np.int32)


def shards_of(ids: Sequence[str], shards: int, routing_shards: int) -> Optional[np.ndarray]:
    """The shard of each id (as ES routes a document by its `_id`), or None if some id can't be hashed here."""
    out = np.empty(len(ids), dtype=np.int64)
    factor = routing_shards // shards
    for start in range(0, len(ids), _BATCH):
        batch = np.asarray(ids[start:start + _BATCH], dtype=object)
        lengths = np.fromiter(map(len, batch), dtype=np.int64, count=len(batch))
        for length in np.unique(lengths):
            idx = np.flatnonzero(lengths == length)
            h = _hash_same_length(batch[idx].tolist(), int(length))
            if h is None:
                return None
            out[start + idx] = np.mod(h.astype(np.int64), routing_shards) // factor
    return out


def default_routing_shards(shards: int) -> int:
    """ES's routing shards for an index created on 7.0 or later that doesn't set them
    (MetadataCreateIndexService.calculateNumRoutingShards): the largest shards * 2^x up to 1024, x at least 1."""
    splits = max(1, 10 - (shards - 1).bit_length())
    return shards << splits


def routing(es, index: str) -> Optional[Tuple[str, int, int]]:
    """(concrete index, shards, routing shards) of `index` (an alias of one index), checked against ES once per
    concrete index and remembered for a minute; None when it can't be routed (several indices, an old index or a
    custom routing, a failed check)."""
    now = time.monotonic()
    hit = _known.get(index)
    if hit is not None and now - hit[0] < _TTL_S:
        return hit[1]
    try:
        got = es.indices.get_settings(index=index, flat_settings=True,
                                      name="index.number_of_shards,index.number_of_routing_shards,"
                                           "index.version.created,index.routing_partition_size").body
    except Exception:   # noqa: BLE001 - routing is only a speed-up
        return None
    found = None
    if len(got) == 1:
        concrete, s = next(iter(got.items()))
        s = s.get("settings") or {}
        if not s.get("index.routing_partition_size") and int(s.get("index.version.created") or 0) >= 7_000_099:
            shards = int(s["index.number_of_shards"])
            rs = int(s.get("index.number_of_routing_shards") or default_routing_shards(shards))
            ok = _checked.get(concrete)
            if ok is None:
                ok = _checked[concrete] = _check(es, concrete, shards, rs)
            found = (concrete, shards, rs) if ok else None
    _known[index] = (now, found)
    return found


def _check(es, index: str, shards: int, rs: int) -> bool:
    """A few documents, each found by its `id` on the shard this module names for it."""
    try:
        hits = es.search(index=index, body={"size": _CHECK_DOCS, "_source": ["id"],
                                            "query": {"match_all": {}}}).body["hits"]["hits"]
        ids = [h["_id"] for h in hits]
        where = shards_of(ids, shards, rs)
        # the filter is on the `id` field: it must be the `_id` documents are routed by
        if not ids or where is None or any((h.get("_source") or {}).get("id") != h["_id"] for h in hits):
            return False
        lines = []
        for doc_id, k in zip(ids, where):
            lines.append({"index": index, "preference": f"_shards:{int(k)}"})
            lines.append({"size": 0, "query": {"term": {"id": doc_id}}})
        res = es.msearch(searches=lines).body["responses"]
        return all(r.get("hits", {}).get("total", {}).get("value") == 1 for r in res)
    except Exception:   # noqa: BLE001
        return False


def group(ids: Sequence[str], where: np.ndarray, shards: int, pieces: int) -> List[Tuple[List[int], List[str]]]:
    """`ids` cut into `pieces` (shards k, k + pieces, ...), each with the shards that hold its ids."""
    key = where % pieces
    arr = np.asarray(ids, dtype=object)
    out = []
    for p in range(pieces):
        idx = np.flatnonzero(key == p)
        if len(idx):
            out.append((list(range(p, shards, pieces)), arr[idx].tolist()))
    return out


def pieces(es, index: str, ids: Sequence[str], n: int) -> Optional[Tuple[str, List[Tuple[List[int], List[str]]]]]:
    """(concrete index, `n` pieces of `ids` each with the shards holding them), or None when `index` can't be
    routed or an id can't be hashed."""
    r = routing(es, index)
    if r is None:
        return None
    concrete, shards, rs = r
    where = shards_of(ids, shards, rs)
    return None if where is None else (concrete, group(ids, where, shards, n))
