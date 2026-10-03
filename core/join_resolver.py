"""Resolve a filter on a related entity's attribute into that entity's ids (oxjob #1526).

A query-time join: `works?filter=primary_location.source.country_code:CA` looks up the ids of
the sources whose `country_code` is CA in the sources index, then filters works by
`primary_location.source.id`. The related indexes (sources, institutions, funders, publishers)
are small, so the lookup takes well under a second, and unlike copying the attribute onto every
work it is never stale. The value semantics are the related entity's own: the lookup runs that
entity's filter field (`sources` `country_code`) on the value, so `CA`, `ca`, `!CA` and `>50`
mean exactly what they mean on `/sources`.

Resolved id lists of up to JOIN_CACHE_MAX_IDS are cached (flask-caching, Redis in production) by entity,
field and value.
"""

import copy
import hashlib

from elasticsearch_dsl import A, Q, Search

import settings
from core.exceptions import APIQueryParamsError

ID_PREFIX = "https://openalex.org/"
TERMS_CHUNK = 60000  # one `terms` clause takes at most 65,536 values (index.max_terms_count)
COMPOSITE_PAGE = 50000  # under search.max_buckets (65,536)


def _entity_fields_and_index(entity):
    """(fields_dict, index) for a related entity; imported lazily (entity field modules import core.fields)."""
    if entity == "sources":
        from sources.fields import fields_dict
        return fields_dict, settings.SOURCES_INDEX
    if entity == "institutions":
        from institutions.fields import fields_dict
        return fields_dict, settings.INSTITUTIONS_INDEX
    if entity == "funders":
        from funders.fields import fields_dict
        return fields_dict, settings.FUNDERS_INDEX
    if entity == "publishers":
        from publishers.fields import fields_dict
        return fields_dict, settings.PUBLISHERS_INDEX
    raise ValueError(f"no query-time join configured for entity {entity!r}")


def _cache():
    from extensions import cache
    return cache


def _cache_key(entity, param, value):
    raw = f"{entity}|{param}|{value}"
    return "join:v1:" + hashlib.sha1(raw.encode()).hexdigest()


def resolve_ids(entity, param, value, label):
    """Full OpenAlex ids of the `entity` rows whose `param` filter matches `value`.

    `value` is one filter value, or a list of values ORed (a collection's members, e.g. the
    countries in a "Latin America" countries collection). `label` is the user-facing filter
    name, for error messages. Raises APIQueryParamsError when the value matches more rows than
    settings.MAX_JOIN_IDS."""
    values = list(value) if isinstance(value, (list, tuple)) else None
    if values is not None:
        value = "|".join(sorted(str(v) for v in values))
    key = _cache_key(entity, param, value)
    try:
        cached = _cache().get(key)
    except Exception:
        cached = None
    if cached is not None:
        return [ID_PREFIX + i for i in cached]

    fields_dict, index = _entity_fields_and_index(entity)
    target = copy.copy(fields_dict[param])  # Field instances are stateful; never mutate the shared one
    if values is not None:
        inner = target.build_terms_query(values)
    else:
        target.value = value
        inner = target.build_query()

    base = Search(index=index).filter(inner)
    total = base.extra(size=0, track_total_hits=True).execute().hits.total.value
    if total > settings.MAX_JOIN_IDS:
        raise APIQueryParamsError(
            f"{label}:{value[:80]} matches {total:,} {entity}, more than the {settings.MAX_JOIN_IDS:,} this filter "
            f"can look up at once. Narrow the value, or filter by the {entity} ids directly."
        )

    short_ids = []
    after = None
    while True:
        s = base.extra(size=0)
        params = {"after": after} if after else {}
        s.aggs.bucket("ids", A("composite", size=COMPOSITE_PAGE, sources=[{"id": {"terms": {"field": "id"}}}], **params))
        res = s.execute().aggregations.ids
        short_ids.extend(b.key.id.replace(ID_PREFIX, "", 1) for b in res.buckets)
        if len(res.buckets) < COMPOSITE_PAGE or "after_key" not in res:
            break
        after = res.after_key.to_dict()

    # Big lists (e.g. an h-index range over most sources) aren't cached: arbitrary range values
    # could otherwise fill Redis with multi-MB entries.
    if len(short_ids) <= settings.JOIN_CACHE_MAX_IDS:
        try:
            _cache().set(key, short_ids, timeout=settings.JOIN_CACHE_SECONDS)
        except Exception:
            pass
    return [ID_PREFIX + i for i in short_ids]


def terms_query(local_field, ids):
    """A filter matching documents whose `local_field` holds any of `ids` (chunked under the clause cap)."""
    if not ids:
        return Q("bool", must_not=[Q("match_all")])
    chunks = [ids[i:i + TERMS_CHUNK] for i in range(0, len(ids), TERMS_CHUNK)]
    if len(chunks) == 1:
        return Q("terms", **{local_field: chunks[0]})
    return Q("bool", should=[Q("terms", **{local_field: c}) for c in chunks], minimum_should_match=1)
