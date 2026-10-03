"""Title + abstract + keywords search (oxjob #1521).

A work matches when the query's words are in its text, as today, OR when a phrase
in the query names one of the work's keywords (by the keyword's display name or one
of its synonyms on the keywords index). Each keyword phrase is satisfied by the text
or by the keyword; every other word must still be in the text; all parts are ANDed,
and the whole rule is ORed with the plain text rule, so a search never returns fewer
works than the text rule alone. Boolean / quoted searches get the same treatment per
term or quoted phrase: `(term OR keywords.id:"…")`.

Works carrying the query's keywords also get a small fixed bonus (KEYWORD_BONUS split
over the query's keyword phrases). Measured in oxjobs #1521 EXPLORE §§ 5-6
(scratch/p1.py `kseg_body`, scratch/p2.py `kw_boost`); this module is that code.

Query-time only: works already carry `keywords.id`; synonyms live on keywords-v1.
"""
import functools
import json
import re
import unicodedata

from elasticsearch_dsl import Q
from elasticsearch_dsl.connections import connections

import settings

KEYWORD_BONUS = 10.0
MAX_SPAN_WORDS = 6
MAX_LOOKUP_TOKENS = 40  # longer plain queries (pasted abstracts) skip the lookup
LOOKUP_TIMEOUT_S = 2

STOP = set(
    "a an and are as at be by for from has have in into is it its of on or that the their this to was were with "
    "vs versus via among between within without about after before during".split()
)
# Lucene's English stop set: the works analyzers drop these, so a span made only of
# them has no text side and must never become a keyword phrase ("NO", "I", "will").
STOP_EN = set(
    "a an and are as at be but by for if in into is it no not of on or such that the their then there these "
    "they this to was will with".split()
)
STOP |= STOP_EN

QS_CHARS = re.compile(r'["()*?~:]|\b(AND|OR|NOT)\b|^\s*-|\s-\w|\+')
QS_LEAF = re.compile(r'"([^"]+)"(~\d+)?|([^\s()"]+)')


def norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", s)).strip()


def variants(span):
    """The spellings a span is looked up under: case-folded, as typed, upper-case
    (acronyms), and singular/plural of the last word."""
    lo = norm(span)
    vs = {lo, span.strip(), span.strip().upper()}
    words = lo.split()
    if words:
        last = words[-1]
        alts = {last + "s", last + "es"}
        if last.endswith("ies"):
            alts.add(last[:-3] + "y")
        if last.endswith("es"):
            alts.add(last[:-2])
        if last.endswith("s") and not last.endswith("ss"):
            alts.add(last[:-1])
        if last.endswith("y"):
            alts.add(last[:-1] + "ies")
        for a in alts:
            vs.add(" ".join(words[:-1] + [a]))
    return {v for v in vs if v}


def lookup(spans):
    """{span: [keyword ids]} for every span whose spelling exactly matches a keyword
    name or synonym. One terms query on keywords-v1. On any error: no keywords."""
    allv = {}
    for s in spans:
        for v in variants(s):
            allv.setdefault(v, set()).add(s)
    out = {s: [] for s in spans}
    if not allv:
        return out
    terms = sorted(allv)
    body = {
        "size": 5000,
        "_source": ["id", "display_name", "display_name_alternatives"],
        "query": {
            "bool": {
                "should": [
                    {"terms": {"display_name.keyword": terms}},
                    {"terms": {"display_name_alternatives.keyword": terms}},
                ]
            }
        },
    }
    try:
        es = connections.get_connection("walden")
        js = es.search(index=settings.KEYWORDS_INDEX, body=body, request_timeout=LOOKUP_TIMEOUT_S)
    except Exception:
        return out
    for h in js["hits"]["hits"]:
        src = h["_source"]
        kid = src["id"]
        for v in [src.get("display_name") or ""] + list(src.get("display_name_alternatives") or []):
            for s in allv.get(v, set()) | allv.get(norm(v), set()):
                if kid not in out[s]:
                    out[s].append(kid)
    return out


def is_query_string(q):
    return bool(QS_CHARS.search(q))


def plain_tokens(q):
    return [t for t in (w.strip(".,;!?\"'()[]{}") for w in q.split()) if t]


def segment(tokens, found):
    """found: {(i, j): [ids]}. Non-overlapping keyword spans, longest first."""
    cands = []
    for (i, j), ids in found.items():
        if not ids:
            continue
        if all(t.lower() in STOP_EN for t in tokens[i:j]):
            continue
        if j - i == 1 and tokens[i].lower() in STOP:
            continue
        cands.append((j - i, i, j))
    cands.sort(key=lambda t: (-t[0], t[1]))
    used, segs = set(), []
    for _, i, j in cands:
        if any(p in used for p in range(i, j)):
            continue
        used.update(range(i, j))
        segs.append((i, j))
    return sorted(segs), used


def query_string_leaves(q):
    """(start, end, text) for each plain term or quoted phrase in a Boolean query.
    Proximity phrases, wildcards, field-qualified terms and stopwords are left alone."""
    leaves = []
    for m in QS_LEAF.finditer(q):
        if m.group(1) is not None:
            if m.group(2):
                continue
            leaves.append((m.start(), m.end(), m.group(1)))
        else:
            w = m.group(3)
            if w in ("AND", "OR", "NOT") or any(c in w for c in "*?:~^+") or w.startswith("-"):
                continue
            if w.lower() in STOP:
                continue
            leaves.append((m.start(), m.end(), w))
    return leaves


@functools.lru_cache(maxsize=20000)
def keyword_record(q):
    """The keyword phrases in a query, as a JSON string (cached per process).

    plain: {"mode": "plain", "segments": [[span, [ids]], ...], "leftover": [words]}
    Boolean: {"mode": "qs", "leaves": [[start, end, text, [ids]], ...]}
    """
    if is_query_string(q):
        leaves = query_string_leaves(q)
        lk = lookup(sorted({t for _, _, t in leaves})) if leaves else {}
        return json.dumps({"mode": "qs", "leaves": [[a, b, t, lk[t]] for a, b, t in leaves if lk.get(t)]})
    toks = plain_tokens(q)
    if not toks or len(toks) > MAX_LOOKUP_TOKENS:
        return json.dumps({"mode": "plain", "segments": [], "leftover": toks})
    spans = {
        (i, j): " ".join(toks[i:j])
        for i in range(len(toks))
        for j in range(i + 1, min(len(toks), i + MAX_SPAN_WORDS) + 1)
    }
    lk = lookup(sorted(set(spans.values())))
    found = {ij: lk.get(s) or [] for ij, s in spans.items()}
    segs, used = segment(toks, found)
    return json.dumps({
        "mode": "plain",
        "segments": [[spans[(i, j)], found[(i, j)]] for i, j in segs],
        "leftover": [t for k, t in enumerate(toks) if k not in used],
    })


def keyword_groups(rec):
    if rec["mode"] == "qs":
        return [ids for _, _, _, ids in rec["leaves"] if ids]
    return [ids for _, ids in rec["segments"] if ids]


def _find_query_string(node):
    if isinstance(node, dict):
        if "query_string" in node:
            return node["query_string"]
        for v in node.values():
            r = _find_query_string(v)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_query_string(v)
            if r is not None:
                return r
    return None


def with_keywords(q, rec, base, text_fields):
    """The keyword rule for query `q` around the text query `base` (an ES dict, no
    citation boost). text_fields: the fields a keyword phrase's text side searches."""
    if rec["mode"] == "qs":
        leaves = rec["leaves"]
        if not leaves:
            return base
        qsn = _find_query_string(base)
        # Leaves were found on the raw query; rewrite only if the builder kept it as typed.
        if qsn is None or qsn.get("query") != q:
            return base
        s, out, pos = qsn["query"], [], 0
        for a, b, _, ids in sorted(leaves):
            out.append(s[pos:a])
            out.append("(" + s[a:b] + " OR " + " OR ".join(f'keywords.id:"{k}"' for k in ids) + ")")
            pos = b
        out.append(s[pos:])
        body = json.loads(json.dumps(base))
        _find_query_string(body)["query"] = "".join(out)
        return body
    if not rec["segments"]:
        return base

    def text(words):
        return {"multi_match": {"query": words, "fields": text_fields, "type": "cross_fields", "operator": "and"}}

    must = [
        {"bool": {"should": [text(span), {"terms": {"keywords.id": ids}}], "minimum_should_match": 1}}
        for span, ids in rec["segments"]
    ]
    left = [t for t in rec["leftover"] if t.lower() not in STOP]
    if left:
        must.append(text(" ".join(left)))
    return {"bool": {"should": [base, {"bool": {"must": must}}], "minimum_should_match": 1}}


def keyword_bonus(query, rec, weight=KEYWORD_BONUS):
    groups = keyword_groups(rec)
    if not groups:
        return query
    return {
        "bool": {
            "must": [query],
            "should": [
                {"constant_score": {"filter": {"terms": {"keywords.id": g}}, "boost": weight / len(groups)}}
                for g in groups
            ],
        }
    }


def text_fields_for(search_type, with_fulltext):
    exact = search_type == "exact"
    fields = ["display_name.no_stem", "abstract.no_stem^0.1"] if exact else ["display_name", "abstract^0.1"]
    if with_fulltext:
        fields.append("fulltext.no_stem^0.05" if exact else "fulltext^0.05")
    return fields


def keyword_search_query(search_terms, base_query, search_type="default", with_fulltext=False,
                         skip_citation_boost=False):
    """Wrap a works text query (built with skip_citation_boost=True) in the keyword
    rule + keyword bonus, then the works citation boost."""
    from core.search import SearchOpenAlex, normalize_search_input

    q = normalize_search_input(search_terms)
    base = base_query.to_dict() if hasattr(base_query, "to_dict") else base_query
    rec = json.loads(keyword_record(q)) if q else {"mode": "plain", "segments": [], "leftover": []}
    body = with_keywords(q, rec, base, text_fields_for(search_type, with_fulltext))
    body = keyword_bonus(body, rec)
    query = Q(body)
    if skip_citation_boost:
        return query
    return SearchOpenAlex.citation_boost_query(query, scaling_type=settings.CITATION_SCALING)
