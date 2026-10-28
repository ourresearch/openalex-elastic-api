#!/usr/bin/env python3
"""Does every registered filter find the record its value came from? (oxjob #1901)

Two checks over every filter on the 26 entities:

  offline (CI, no Elasticsearch):  --check-index-fields
      Render each filter's query and check every field it names is in docs/index-fields.json,
      the field list of the live indexes. A filter on a field the index doesn't have answers a
      silent 0 for every value (topics_count, is_in_jstage, primary_location.raw_type.lower...).
      Refresh the list after an index rebuild with --write-index-fields (needs $ES_URL_WALDEN).

  live (needs $ES_URL_WALDEN):  default
      For each filter, take 5 random records that hold the queried field (seed 1901), turn each
      record's own value into a filter value, and ask the live API (or --local: this checkout's
      app on the live cluster) for the count. Pass = count >= 1, or a JSON 400 refusal.
      Each sample scores a whole index (random_score): ~2 min of cluster load, so run it off-peak.

Verdicts: ok | refused (JSON 400, by design) | silent_zero | partial (some records' values 0) |
error (5xx / non-JSON) | no_data (no record holds the field) | expected_zero | skip (collection/join).

  PYTHONPATH=. venv/bin/python scripts/filter_sweep.py [--base https://api.openalex.org | --local]
      [--out results.json] [--entity works] [--param doi]
  PYTHONPATH=. venv/bin/python scripts/filter_sweep.py --check-index-fields
"""
import argparse
import copy
import importlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

for k, v in {
    "REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
    "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
    "USERS_DB_URL": "postgresql://u:p@localhost:5432/db", "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "JWT_SECRET_KEY": "x", "SECRET_KEY": "x", "USERS_API_URL": "http://localhost.test",
}.items():
    os.environ.setdefault(k, v)
sys.path.insert(0, os.getcwd())
import country_list  # noqa: E402
from core.properties import ENTITY_FIELDS_MODULES  # noqa: E402

INDEX_FIELDS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "index-fields.json")
SEED = 1901
N_RECORDS = 5
CONTINENT_OF = {c["country_code"].upper(): cont.lower().replace(" ", "_")
                for cont, cs in country_list.COUNTRIES_BY_CONTINENT.items() for c in cs}
LEAF = {"term", "terms", "prefix", "range", "wildcard", "regexp", "fuzzy", "match", "match_phrase",
        "match_phrase_prefix", "match_bool_prefix", "term_set", "intervals", "span_term"}
MULTI = {"multi_match", "query_string", "simple_query_string", "combined_fields"}
SKIP_CLASSES = {"CollectionField", "JoinField"}  # values come from users-api / another entity
# A 0 that is the right answer, checked by hand.
EXPECTED_ZERO = {
    ("works", "has_old_authors"): "true matches no work: 0 author ids before A5 remain in works or authors (ES count, 2026-10-28)",
}
# Records the API hides by default, so a value taken from them can't be expected to return them.
HIDDEN = {"works": {"term": {"is_xpac": True}},           # xpac works need include_xpac
          "authors": {"term": {"works_count": 0}}}         # authors/views.py default works_count:>0
SUBFIELD_SUFFIXES = (".keyword", ".lower", ".search", ".exact", ".en", ".folded", ".raw", ".text", ".sort")
# A value of the right shape for each filter class, to render its query (and per param where the class's won't do).
DUMMY = {
    "BooleanField": ["true"], "DateField": ["2020-01-01"], "DateTimeField": ["2020-01-01"],
    "RangeField": ["5", "2020"], "SearchField": ["cancer"], "PhraseField": ["cancer"],
    "OpenAlexIDField": ["W2741809807", "A5023888391", "I27837315", "S137773608", "T10001", "C41008148",
                        "F4320332161", "P4310320990"],
    "ExternalIDField": ["x"], "OrcidField": ["0000-0002-1825-0097"],
}
DUMMY_BY_PARAM = {"best_open_version": ["any"], "parent_awards.id": ["G1423019346"],
                  "sub_awards.id": ["G1423019346"], "awards.id": ["G1423019346"]}

_ES = None


def index_name(entity):
    """The live index an entity reads (looked up on use: some unit tests swap in a fake settings)."""
    import settings
    return settings.AUTHORS_INDEX_WALDEN if entity == "authors" else getattr(settings, entity.upper().replace("-", "_") + "_INDEX")


def es():
    """The live cluster, connected on first use (the offline check never needs it)."""
    global _ES
    if _ES is None:
        from elasticsearch import Elasticsearch
        from elasticsearch_dsl import connections
        _ES = Elasticsearch(os.environ["ES_URL_WALDEN"], request_timeout=120)
        connections.create_connection(hosts=[os.environ["ES_URL_WALDEN"]], request_timeout=60)  # merged-id lookups
    return _ES


def registry(only=None):
    for e, m in ENTITY_FIELDS_MODULES.items():
        if only and e not in only:
            continue
        mod = importlib.import_module(m)
        fd = getattr(mod, "fields_dict", None) or {f.param: f for f in mod.fields}
        for p in sorted(fd):
            yield e, p, fd[p]


# ---------- index mappings ----------
def flat_mapping(index):
    """{dotted field path: type} for every field and sub-field of a live index, and its nested paths."""
    body = next(iter(es().indices.get_mapping(index=index).body.values()))
    out, nested = {}, set()

    def walk(props, prefix=""):
        for name, p in (props or {}).items():
            path = prefix + name
            t = p.get("type", "object")
            out[path] = t
            if t == "nested":
                nested.add(path)
            for sub, sp in (p.get("fields") or {}).items():
                out[path + "." + sub] = sp.get("type")
            if "properties" in p:
                walk(p["properties"], path + ".")
    walk(body["mappings"].get("properties"))
    return out, nested


def in_mapping(path, mp):
    return path in mp or any(k.startswith(path + ".") for k in mp)


# ---------- which fields does a filter query? ----------
def query_fields(d, out):
    if isinstance(d, dict):
        for k, v in d.items():
            if k in LEAF and isinstance(v, dict):
                out.update(fk for fk in v if fk not in ("boost", "_name"))
            elif k == "exists" and isinstance(v, dict):
                out.add(v.get("field"))
            elif k in MULTI and isinstance(v, dict):
                out.update(f.split("^")[0] for f in v.get("fields", []) or [])
                if v.get("default_field"):
                    out.add(v["default_field"])
            elif k == "script":
                out.add("<script>")
            else:
                query_fields(v, out)
    elif isinstance(d, list):
        for x in d:
            query_fields(x, out)
    return out


EXACT = {"term", "terms", "prefix", "wildcard", "regexp"}


def exact_on_text(d, types, out):
    """Fields an exact-value query (term, prefix...) reads as analyzed text: it matches only a single
    lowercase word, so a real value ("Hayashi", a whole DOI) answers 0 (oxjob #1901)."""
    if isinstance(d, dict):
        for k, v in d.items():
            if k in EXACT and isinstance(v, dict):
                out.update(fk for fk in v if types.get(fk) == "text")
            else:
                exact_on_text(v, types, out)
    elif isinstance(d, list):
        for x in d:
            exact_on_text(x, types, out)
    return out


def render(f, value):
    g = copy.copy(f)
    g.value = value
    q = g.build_query()
    return q.to_dict() if hasattr(q, "to_dict") else q


def dummy_values(f):
    if "continent" in f.param:
        return ["europe"]
    return DUMMY_BY_PARAM.get(f.param) or DUMMY.get(type(f).__name__, ["x", "us", "en", "true", "5", "2020-01-01"])


def static_query(f):
    """(rendered query, fields it names, error) for the first typed dummy value that renders."""
    errs = []
    for v in dummy_values(f):
        try:
            d = render(f, v)
            fl = {x for x in query_fields(d, set()) if x}
            if fl:
                return d, sorted(fl), None
        except Exception as ex:  # noqa: BLE001
            errs.append(f"{v!r}: {type(ex).__name__}: {str(ex)[:120]}")
    return None, [], "; ".join(errs)[:400]


def write_index_fields():
    snap = {e: flat_mapping(index_name(e))[0] for e in ENTITY_FIELDS_MODULES}
    with open(INDEX_FIELDS_PATH, "w") as fh:
        json.dump({"indexes": {e: index_name(e) for e in snap}, "fields": snap}, fh, indent=0, sort_keys=True)
        fh.write("\n")
    return sum(len(v) for v in snap.values())


def index_field_problems():
    """[(entity, filter, problem)] for every filter that can run (offline): a field the index doesn't
    have, or an exact-value query on an analyzed text field."""
    with open(INDEX_FIELDS_PATH) as fh:
        snap = json.load(fh)["fields"]  # {entity: {field path: type}}
    logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given
    problems = []
    for e, p, f in registry():
        if type(f).__name__ in SKIP_CLASSES or f.filter_refusal:
            continue
        d, fields, _ = static_query(f)
        missing = [x for x in fields if x != "<script>" and not in_mapping(x, snap[e])]
        if missing:
            problems.append((e, p, f"queries {missing}, not in the index"))
        text = sorted(exact_on_text(d, snap[e], set()))
        if text:
            problems.append((e, p, f"exact-value query on text field {text}"))
    return problems


# ---------- sampling real values ----------
def strip_sub(path, mp):
    for s in SUBFIELD_SUFFIXES:
        if path.endswith(s) and path[: -len(s)] in mp:
            return path[: -len(s)]
    return path


def nested_parent(path, nested):
    best = None
    for n in nested:
        if path.startswith(n + ".") and (best is None or len(n) > len(best)):
            best = n
    return best


def collect(obj, parts):
    """Values at a dotted path inside the fields-API / _source structure."""
    if not parts:
        return obj if isinstance(obj, list) else [obj]
    if isinstance(obj, list):
        out = []
        for x in obj:
            out += collect(x, parts)
        return out
    if isinstance(obj, dict):
        for i in range(len(parts), 0, -1):  # the fields API keeps dotted keys: longest first
            key = ".".join(parts[:i])
            if key in obj:
                return collect(obj[key], parts[i:])
    return []


def sample_values(entity, field, mp, nested, extra_query=None):
    """N_RECORDS random records holding `field` that the API serves by default: [(id, [values])]."""
    base = strip_sub(field, mp)
    np_ = nested_parent(field, nested)
    exists = {"exists": {"field": field}}
    if np_:
        exists = {"nested": {"path": np_, "query": exists}}
    must = [exists] + ([extra_query] if extra_query else [])
    must_not = [HIDDEN[entity]] if entity in HIDDEN else []
    body = {
        "size": N_RECORDS, "_source": [base], "fields": [field, base],
        "query": {"function_score": {"query": {"bool": {"must": must, "must_not": must_not}},
                                     "random_score": {"seed": SEED, "field": "_seq_no"}, "boost_mode": "replace"}},
    }
    out = []
    for h in es().search(index=index_name(entity), body=body)["hits"]["hits"]:
        candidates = ([v for v in collect(src, p.split(".")) if v is not None and v != ""]
                      for src in (h.get("fields") or {}, h.get("_source") or {}) for p in (field, base))
        out.append((h["_id"], next((vals for vals in candidates if vals), [])))
    return out


def to_filter_values(f, vals):
    cls = type(f).__name__
    out = []
    for v in vals:
        if isinstance(v, (dict, list)):
            continue
        if cls == "OpenAlexIDField":
            out.append(str(v).replace("https://openalex.org/", ""))
        elif cls == "RangeField":
            if isinstance(v, bool):
                continue
            try:
                x = float(v)
            except Exception:  # noqa: BLE001
                continue
            out.append(str(int(x)) if x.is_integer() else ("~" + repr(x)))
        elif cls == "DateField":
            out.append(str(v)[:10])
        elif cls == "DateTimeField":
            out.append(str(v).replace("Z", ""))
        elif cls in ("SearchField", "PhraseField"):
            words = sorted({w for w in re.split(r"\W+", str(v)) if len(w) >= 4 and w.isalpha()}, key=lambda w: (-len(w), w))
            if words:
                out.append(words[0].lower())
        elif "continent" in f.param and cls == "TermField":
            if CONTINENT_OF.get(str(v).upper()):
                out.append(CONTINENT_OF[str(v).upper()])
        elif cls == "BooleanField":
            out.append(str(v).lower() if isinstance(v, bool) or str(v).lower() in ("true", "false") else "true")
        else:
            s = str(v)
            if any(c in s for c in ",|") or s[:1] in "!<>":
                continue
            out.append(s)
    return list(dict.fromkeys(out))


# ---------- API ----------
class Api:
    def __init__(self, base, local):
        self.local = local
        if local:
            from app import create_app
            self.client = create_app().test_client()
        else:
            import requests
            self.sess = requests.Session()
            self.base = base
            self.key = os.environ.get("OPENALEX_API_KEY", "")

    def count(self, entity, filt):
        """(HTTP status, count or None, error message)"""
        params = {"filter": filt, "per_page": 1, "select": "id"}
        if self.local:
            r = self.client.get(f"/{entity}", query_string=params)
            body = r.get_json(silent=True) if (r.content_type or "").startswith("application/json") else None
            st = r.status_code
        else:
            params["api_key"] = self.key
            body, st = None, None
            for attempt in range(4):
                try:
                    r = self.sess.get(f"{self.base}/{entity}", params=params, timeout=90)
                    st = r.status_code
                    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
                    if st in (429, 502, 503, 504):
                        time.sleep(2 + 3 * attempt)
                        continue
                    break
                except Exception as ex:  # noqa: BLE001
                    st, body = -1, {"message": str(ex)[:200]}
                    time.sleep(2 + 3 * attempt)
        if st == 200 and body and "meta" in body:
            return st, body["meta"].get("count"), ""
        return st, None, str((body or {}).get("message") or (body or {}).get("error") or "")[:240]


def filter_string(param, fv):
    if " " in fv and "search" not in param:  # a space means AND unless the value is quoted
        return f'{param}:"{fv}"'
    if fv.startswith("~"):  # a float: a narrow range around it
        x = float(fv[1:])
        d = max(abs(x) * 1e-6, 1e-9)
        return f"{param}:>{x - d},{param}:<{x + d}"
    return f"{param}:{fv}"


# ---------- one (entity, filter) ----------
def check(api, entity, param, f, mp, nested):
    cls = type(f).__name__
    row = {"entity": entity, "param": param, "class": cls, "fields": [], "missing": [], "verdict": None,
           "detail": [], "static_err": None}
    if cls in SKIP_CLASSES:
        row["verdict"] = "skip"
        return row
    if f.filter_refusal:  # no stored value: must answer a JSON 400, not a 0
        return probe(api, row, entity, param, [dummy_values(f)[:1]])
    _, fields, err = static_query(f)
    row["fields"], row["static_err"] = fields, err
    real = [x for x in fields if x != "<script>"]
    row["missing"] = missing = [x for x in real if not in_mapping(x, mp)]
    present = [x for x in real if x not in missing]

    if param in ("cited_by", "related_to") and entity == "works":
        # link filters take a work id whose own references / related list holds the results
        recs = sample_values(entity, "referenced_works" if param == "cited_by" else "related_works", mp, nested)
        return probe(api, row, entity, param, [[rid.rsplit("/", 1)[-1]] for rid, _ in recs])
    if real and not present:
        row["verdict"] = "silent_zero"
        row["detail"].append("no queried field in the index mapping")
        return row
    if not real:
        row["verdict"] = "static_unknown"
        return row
    if (entity, param) in EXPECTED_ZERO:
        row["verdict"] = "expected_zero"
        row["detail"].append(EXPECTED_ZERO[(entity, param)])
        return row
    extra = None  # sample records the filter's own constraint admits (journal: the source is a journal)
    if cls in ("OpenAlexIDField", "TermField"):
        try:
            d = render(f, "!null")
            if "must_not" not in json.dumps(d) and len(query_fields(d, set())) > 1:
                extra = d
        except Exception:  # noqa: BLE001
            pass
    want = f.es_field().replace("__", ".")
    order = ([want] if want in present else []) + [x for x in present if x != want]
    recs = []
    for cand in order:  # the field the filter is named for first, then any other it searches
        try:
            recs = sample_values(entity, cand, mp, nested, extra_query=extra)
        except Exception as ex:  # noqa: BLE001
            row["verdict"] = "sample_error"
            row["detail"].append(str(ex)[:200])
            return row
        if recs:
            sf = cand
            break
    if not recs:
        row["verdict"] = "no_data"
        row["detail"].append(f"0 records hold any of {order}")
        return row
    vals = [v for v in (to_filter_values(f, v)[:3] for _, v in recs) if v]
    if not vals:
        row["verdict"] = "no_value"
        row["detail"].append(f"sampled {sf} but could not turn values into filter values: {recs[:2]}")
        return row
    row["sampled_field"] = sf
    return probe(api, row, entity, param, vals)


def probe(api, row, entity, param, vals):
    hits = zeros = refused = errors = 0
    for per_record in vals:  # a record passes if any of its first 3 values returns >= 1
        last = None
        for fv in per_record:
            st, c, msg = api.count(entity, filter_string(param, fv))
            last = (fv, st, c, msg)
            if st == 200 and c and c >= 1:
                hits += 1
                break
        else:
            fv, st, c, msg = last
            if st == 200:
                zeros += 1
            elif st == 400:
                refused += 1
            else:
                errors += 1
            row["detail"].append({"value": fv, "status": st, "count": c, "msg": msg})
    n = len(vals)
    row.update(n=n, hits=hits, zeros=zeros, refused=refused, errors=errors)
    if errors:
        row["verdict"] = "error"
    elif zeros == 0:
        row["verdict"] = "ok" if hits else "refused"
    else:
        row["verdict"] = "silent_zero" if zeros == n else "partial"
    return row


FAILING = ("silent_zero", "partial", "error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://api.openalex.org")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--entity", action="append")
    ap.add_argument("--param", action="append")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--check-index-fields", action="store_true")
    ap.add_argument("--write-index-fields", action="store_true")
    a = ap.parse_args()
    if a.write_index_fields:
        print(f"wrote {write_index_fields()} field paths on {len(ENTITY_FIELDS_MODULES)} indexes to {INDEX_FIELDS_PATH}")
        return 0
    if a.check_index_fields:
        problems = index_field_problems()
        for e, p, problem in problems:
            print(f"FAIL {e} {p}: {problem}")
        print(f"{len(problems)} filter problems against {os.path.relpath(INDEX_FIELDS_PATH)} "
              f"(refresh it after an index rebuild: --write-index-fields)")
        return 1 if problems else 0

    logging.getLogger().setLevel(logging.CRITICAL)
    api = Api(a.base, a.local)
    maps = {e: flat_mapping(index_name(e)) for e in ENTITY_FIELDS_MODULES if not a.entity or e in a.entity}
    jobs = [(e, p, f) for e, p, f in registry(a.entity) if not a.param or p in a.param]
    t0 = time.time()

    def run(j):
        e, p, f = j
        try:
            return check(api, e, p, f, *maps[e])
        except Exception as ex:  # noqa: BLE001
            return {"entity": e, "param": p, "class": type(f).__name__, "verdict": "sweep_error",
                    "detail": [f"{type(ex).__name__}: {str(ex)[:200]}"]}

    with ThreadPoolExecutor(1 if a.local else a.threads) as ex:
        rows = list(ex.map(run, jobs))
    c = Counter(r["verdict"] for r in rows)
    testable = sum(v for k, v in c.items() if k != "skip")
    failing = sum(c[k] for k in FAILING)
    print(f"{len(rows)} (entity, filter) pairs in {time.time() - t0:.0f}s: {dict(c)}")
    print(f"FAILING: {failing} of {testable} testable (silent_zero + partial + error)")
    for r in sorted((r for r in rows if r["verdict"] not in ("ok", "refused", "skip", "expected_zero")),
                    key=lambda r: (r["verdict"], r["entity"], r["param"])):
        print(f"{r['verdict']:12} {r['entity']:12} {r['param']:48} {r.get('class', ''):16} "
              f"missing={r.get('missing')} hits={r.get('hits')}/{r.get('n')} {json.dumps((r.get('detail') or [])[:2])[:300]}")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump({"run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "base": "local" if a.local else a.base,
                       "seed": SEED, "counts": dict(c), "failing": failing, "testable": testable, "rows": rows},
                      fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
