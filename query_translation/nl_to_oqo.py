#!/usr/bin/env python
"""NL → OQO via Claude tool-calling  (oxjob #344, the pipeline brain).

A plain-English question → a validated, canonical OQO. The model emits OQO via
a `submit_oqo` tool and resolves named entities (institutions, funders, topics,
authors, sources) to OpenAlex IDs via a `resolve_entity` tool backed by the live
`/autocomplete` API — so output is structurally valid + canonical by
construction, and entity disambiguation is grounded in real data.

Design (EXPLORE §2/§4):
  * Haiku 4.5 by default; Sonnet is the drop-in fallback (both under the 1¢ cap).
  * Prompt-CACHE the static prefix (system + compact registry + tool defs); the
    user question goes LAST, in the messages — never interpolate it into the
    cached prefix. Verify caching via usage.cache_read_input_tokens.
  * The output OQO drops onto the existing rails: validator → canonicalizer →
    POST /query. This module returns the validated, canonical OQO + usage; it
    does NOT execute (run_eval / the Flask route do that).

Promoted from oxjob #344's job dir (`work/nl_to_oqo.py`) after clearing the eval
quality bar (eval_full6: easy 92.6% / hard 83.7%). Exposed via the
`/query/natural-language/<q>` translation route in `views.py`. Do NOT reuse the
abandoned OpenAI path that previously backed that route.

Env: CLAUDE_API_KEY (or ANTHROPIC_API_KEY). The Flask route lazy-imports this
module and returns 503 if neither is set, so the dependency is soft.
"""
import json
import os
import urllib.parse
import urllib.request

from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.validator import validate_oqo

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
OPENALEX_API = os.environ.get("OPENALEX_API_BASE", "https://api.openalex.org")
REGISTRY_ENTITIES = ["works", "authors", "sources", "institutions", "topics"]

MAX_TOOL_TURNS = 8

_REGISTRY_CACHE = None


# ---------------------------------------------------------------------------
# Registry (the grounding) — filter/group_by/sort columns per entity, built
# IN-PROCESS from the property catalog (same source as the /registry route), so
# there's no HTTP self-call and it can never go stale relative to the catalog.
# ---------------------------------------------------------------------------
def load_registry(refresh=False):
    """Return {entity: {col: meta}} for REGISTRY_ENTITIES. Cached in-process."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and not refresh:
        return _REGISTRY_CACHE
    from core.properties import render_properties
    reg = {}
    for entity in REGISTRY_ENTITIES:
        rendered = render_properties(entity=entity)
        reg[entity] = rendered["properties"][entity]
    _REGISTRY_CACHE = reg
    return reg


def compact_registry_text(registry):
    """One compact line per filterable/groupable/sortable column, per entity.
    `->entity` marks an entity-valued column (resolve names to IDs via the tool)."""
    out = []
    for entity in REGISTRY_ENTITIES:
        props = registry.get(entity, {})
        lines = []
        for name, meta in sorted(props.items()):
            actions = meta.get("actions", [])
            if not any(a in actions for a in ("filter", "group_by", "sort", "search")):
                continue
            ops = meta.get("operators", [])
            tags = []
            if "filter" in actions:
                tags.append("filter")
            if "group_by" in actions:
                tags.append("group")
            if "sort" in actions:
                tags.append("sort")
            et = meta.get("entity_type")
            ent_tag = f" ->{et}" if et else ""
            typ = meta.get("type") or "?"
            lines.append(f"  {name} ({typ}) ops={'/'.join(ops) or '-'} [{','.join(tags)}]{ent_tag}")
        out.append(f"## {entity}\n" + "\n".join(lines))
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# System prompt — OQO format + the search mini-language + synthetic examples.
# (Examples are SYNTHETIC, not drawn from the eval corpus, to avoid leakage.)
# ---------------------------------------------------------------------------
SYSTEM_RULES = r"""You translate a user's natural-language search request about scholarly works into an OpenAlex Query Object (OQO), then call submit_oqo exactly once.

# OQO shape
{
  "get_rows": "<entity>",                # works | authors | sources | institutions | topics
  "filter_rows": [ <filter>, ... ],      # implicitly AND-ed together
  "sort_by":  [ {"column_id": "<col>", "direction": "asc"|"desc"} ],   # optional, ordered
  "group_by": [ {"column_id": "<col>"} ],                              # optional
  "sample":   <int>                       # optional
}
A <filter> is either a LEAF or a BRANCH:
  LEAF:   {"column_id": "<col>", "value": <scalar>, "operator": "is", "is_negated": false}
  BRANCH: {"join": "and"|"or", "filters": [ <filter>, ... ]}
Operators: "is" (default; equality/entity/enum/bool), ">" ">=" "<" "<=" (numbers/years), "has" (search columns only). For equality use "is" or simply OMIT the operator — NEVER "=" or "==" (those are invalid and will be rejected). Negate a leaf with "is_negated": true (this is the ONLY negation mechanism — there is no "is not" operator).

# Values
- Entity-valued columns (marked ->entity in the registry, e.g. institution/funder/topic/author/source) take a SHORT OpenAlex id (e.g. "I136199984", "F4320332161", "T10895"). You MUST resolve names to ids with resolve_entity — never guess an id.
- Country codes are 2-letter UPPERCASE ISO ("US","FR","BR"); enum slugs are lowercase ("article","gold","journal"); language is a 2-letter code ("en","es","fr"); booleans are true/false; years/counts are integers.
- Work `type` enum is EXACTLY one of: article, review, preprint, book, book-chapter, dataset, dissertation, report, letter, editorial, erratum, paratext, libguides, reference-entry, peer-review, standard, retraction, supplementary-materials, other. Map phrasings: "journal article"/"research article"/"paper"/"conference paper" -> "article"; "review article" -> "review". There is NO "journal-article" value (that's a Crossref slug — do not use it).

# Search columns (text search) and the value mini-language
Pick the search column by SCOPE, and the variant by exactness:
- title only:            display_name.search   (stemmed) | display_name.search.exact (exact)
- title AND abstract:    title_and_abstract.search | title_and_abstract.search.exact
- abstract only:         abstract.search | abstract.search.exact
- anywhere/full text:    default.search
- author byline:         raw_author_name.search
- raw affiliation text:  raw_affiliation_strings.search
All search leaves use operator "has". Encode the user's intent in the VALUE.

## Multi-word terms: near-phrase by DEFAULT
A multi-word search term is, by default, ONE stemmed near-phrase — a single leaf on the .search column whose value is the phrase wrapped in escaped double-quotes, e.g. "\"climate change\"". It matches the words adjacent and in order, but stemmed (plurals/tenses). Bare "coral bleaching", "machine learning", "genome editing", "quantum computing" -> ONE near-phrase leaf. This is what users almost always mean — do NOT split a bare phrase into separate words.
- Split into one leaf PER WORD (e.g. value "climate" AND value "change", two leaves AND-ed) ONLY when the user EXPLICITLY wants the words separately: "the word climate and the word change", "climate and change as separate words", "both terms anywhere, not necessarily together". Default to the near-phrase otherwise.
- A single word is just one leaf, bare value, e.g. value "graphene".

## Exactness: STRONGLY prefer stemmed; exact is rare
Use the .search column (stemmed) UNLESS there is a strong, explicit exactness signal — the user says "exact", "exactly", "literal", "literally", "no stemming", "no plurals", "no variations", or quotes the term AND calls it exact. Without such a signal, ALWAYS use stemmed .search (even if the user used quotes for emphasis). Exact, non-stemmed search is an unusual ask — resist it.
- Exact phrase (signal present): .search.exact column, value = phrase in escaped quotes, e.g. "\"machine learning\"".
- Exact SINGLE word (signal present): .search.exact column, value = the bare word with NO quotes, e.g. "cat".

## Literal phrases containing and/or/not
A user-quoted phrase is ONE value even if it contains the words "and", "or", "not". "the phrase \"rock or roll\"" -> ONE leaf, value "\"rock or roll\"" — NEVER split it into a boolean rock OR roll. Words like and/or/not INSIDE a quoted phrase are part of the phrase, not operators.

## Proximity ("within N words")
Append ~N to the quoted phrase value: "\"smart phone\"~3". Use .search.exact for exact proximity, .search for stemmed proximity.

## Wildcards (pattern matching) — use the .search.exact column
A wildcard pattern is NOT stemmed, so it goes on the .search.exact column (e.g. display_name.search.exact, title_and_abstract.search.exact), value = the bare pattern:
- trailing: a word "starting with"/"beginning with" X -> value "X*" (e.g. "phone*" matches phone, phones, phoneme, phonetic).
- single-char: exactly one variable character -> "wo?d" (e.g. "wom?n" matches woman/women).
- mid-word: one token starting foo and ending bar -> "foo*bar".
Use a wildcard when the user describes a word PATTERN/PREFIX. For two known spellings ("US or UK spelling"), prefer an explicit OR of the two words over a mid-word wildcard.

## Boolean / exclusion / conjoined terms
- Boolean groups ("A and (B or C)"): a leaf for A AND a {"join":"or",...} branch for (B or C).
- Terms joined by an EXPLICIT conjunction are SEPARATE search leaves, not a phrase: "CRISPR and Cas9" -> two AND-ed leaves (value "CRISPR", value "Cas9"); "supply or demand chain" -> an {"join":"or"} branch. Only a bare adjacent multi-word concept with NO conjunction is a near-phrase.
- Single-valued columns (type, language, oa_status, is_oa): a work has exactly ONE value, so MULTIPLE values always mean "is any of" — an {"join":"or"} branch — EVEN when the user says "and". "articles and reviews" -> {"join":"or","filters":[{type:article},{type:review}]} (never two AND-ed type leaves, which match nothing).
- Exclusion ("but not X"/"does not mention X"): a search leaf with "is_negated": true.

# Negated sets (De Morgan — IMPORTANT)
"not A or B", "not any of (A, B)", "exclude A and B", "neither A nor B" all mean NONE of them match. That is NOT(A or B) = (NOT A) AND (NOT B): emit a SEPARATE negated leaf per value, AND-ed together (two top-level leaves, each "is_negated": true). NEVER emit "(NOT A) OR (NOT B)" — that matches almost everything and is wrong.
e.g. "papers not from MIT or Stanford" -> {"get_rows":"works","filter_rows":[{"column_id":"authorships.institutions.lineage","value":"<mit>","is_negated":true},{"column_id":"authorships.institutions.lineage","value":"<stanford>","is_negated":true}]}

# Examples (synthetic — follow the SHAPE, not the words)
"papers from MIT" -> resolve_entity("institutions","MIT") -> {"get_rows":"works","filter_rows":[{"column_id":"authorships.institutions.lineage","value":"<id>"}]}
"open access reviews since 2021" -> {"get_rows":"works","filter_rows":[{"column_id":"open_access.is_oa","value":true},{"column_id":"type","value":"review"},{"column_id":"publication_year","value":2021,"operator":">="}]}
"papers about spin glass" (multi-word, NO exact signal -> near-phrase, stemmed) -> {"get_rows":"works","filter_rows":[{"column_id":"title_and_abstract.search","value":"\"spin glass\"","operator":"has"}]}
"the exact phrase \"spin glass\" in title or abstract" (exact signal) -> {"get_rows":"works","filter_rows":[{"column_id":"title_and_abstract.search.exact","value":"\"spin glass\"","operator":"has"}]}
"most cited papers about graphene" (single word) -> {"get_rows":"works","filter_rows":[{"column_id":"title_and_abstract.search","value":"graphene","operator":"has"}],"sort_by":[{"column_id":"cited_by_count","direction":"desc"}]}
"count papers per country about graphene" -> {"get_rows":"works","filter_rows":[{"column_id":"title_and_abstract.search","value":"graphene","operator":"has"}],"group_by":[{"column_id":"authorships.countries"}]}
"papers from EU27 countries" (a COLLECTION) -> cannot_translate("collections like EU27 are not supported in NL v1")

# Common column choices (prefer these — don't invent variants)
- A research-subject term ("CRISPR", "quantum computing", "machine learning", "coral bleaching") is a TEXT SEARCH (title_and_abstract.search or default.search) by DEFAULT — do NOT resolve it to primary_topic.id. Only use primary_topic.id when the user explicitly says "topic" or supplies a topic id (T…).
- Filter WORKS by an institution: authorships.institutions.lineage. By an author: authorships.author.id. By a funder: funders.id. By a topic: primary_topic.id (NEVER concepts.id / x_concepts.id — deprecated).
- Filter AUTHORS by their institution: last_known_institutions.id. By country: last_known_institutions.country_code. By topic: topics.id.
- "group by ..." dimensions (works): author -> authorships.author.id; co-author -> authorships.author.id; institution -> authorships.institutions.lineage; country -> authorships.countries; source/journal -> primary_location.source.id; funder -> funders.id; topic -> primary_topic.id; field -> primary_topic.field.id; SDG -> sustainable_development_goals.id; year -> publication_year.
- An OpenAlex id in the request tells you the entity: I…=institution, A…=author, F…=funder, T…=topic, S…=source, W…=work. "author A5…" with no other intent means get_rows=authors filtered by ids.openalex.

# Rules
- Resolve EVERY named entity with resolve_entity before submitting; prefer the FIRST (most relevant) candidate unless the request clearly points to another.
- Prefer the simplest OQO that captures the intent. Omit optional keys you don't need.
- Default get_rows is "works" unless the user clearly asks for authors/sources/institutions/topics.
- group_by auto-sorts its buckets by works_count descending. When you emit a group_by, do NOT add a sort_by — it orders rows, not groups, and a sort_by together with a group_by is INVALID and will be rejected. So "which X has the most", "top X", "ranked", "most" UNDER a group_by needs NO sort_by — the buckets already come back ordered by count. (Only add sort_by for ungrouped row queries.)
- Collections (named multi-member groups of countries/institutions: EU27, the EU, G7, BRICS, "col_...", "the Global South") are NOT supported — call cannot_translate instead of guessing. Individual countries/institutions ARE fine.
- Call submit_oqo exactly once with the final OQO (or cannot_translate). Do not include prose.

# Available columns (registry)
"""


def build_system_blocks(registry):
    """System as cacheable content blocks; the big registry block gets the cache breakpoint."""
    reg_text = compact_registry_text(registry)
    return [
        {"type": "text", "text": SYSTEM_RULES},
        {"type": "text", "text": reg_text, "cache_control": {"type": "ephemeral"}},
    ]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "resolve_entity",
        "description": "Resolve a named entity (institution, funder, topic, author, source, publisher) to OpenAlex candidate ids via relevance search. Returns up to 5 {id, display_name, hint} candidates ranked by relevance — the FIRST is the best match. Use the short id (e.g. I136199984) in the OQO.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string",
                                "description": "plural entity type: institutions, funders, topics, authors, sources, publishers, concepts"},
                "query": {"type": "string", "description": "the name to look up"},
            },
            "required": ["entity_type", "query"],
        },
    },
    {
        "name": "submit_oqo",
        "description": "Submit the final OpenAlex Query Object. Call exactly once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "oqo": {"type": "object", "description": "the OQO dict (get_rows, filter_rows, optional sort_by/group_by/sample)"},
            },
            "required": ["oqo"],
        },
    },
    {
        "name": "cannot_translate",
        "description": "Call this INSTEAD of submit_oqo when the request cannot be expressed as an OQO in NL v1. The main case is a COLLECTION reference — a named, predefined group of countries or institutions (e.g. 'EU27', 'the EU', 'G7', 'BRICS', 'col_eu27', 'the Global South'). Individual countries/institutions are fine; only named multi-member collections are unsupported. Give a short reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "brief explanation of why it can't be translated"},
            },
            "required": ["reason"],
        },
    },
]


def _short_id(oa_id):
    return oa_id.rsplit("/", 1)[-1] if isinstance(oa_id, str) else oa_id


# Plural entity type -> API list path. Every type resolves through the proper
# relevance ?search= endpoint, NOT /autocomplete: autocomplete is a data-poor
# shadow of the real search filters and mis-ranks (e.g. it surfaced the WRONG
# Stephen Hawking — a 16-work namesake — while ?search= ranks the real
# A5066175077 first). Jason 2026-06-05: "we should NEVER use autocomplete."
_RESOLVE_PATHS = {
    "institutions": "institutions", "funders": "funders", "topics": "topics",
    "authors": "authors", "sources": "sources", "publishers": "publishers",
    "concepts": "concepts",
}


def resolve_entity_call(entity_type, query, limit=5):
    """Resolve a name to OpenAlex candidate ids via the live relevance ?search=
    endpoint (ranked by relevance_score desc), returning compact candidates with
    short ids. The FIRST candidate is the best match."""
    et = entity_type.strip().lower()
    path = _RESOLVE_PATHS.get(et, et)
    qs = urllib.parse.urlencode({
        "search": query,
        "select": "id,display_name,works_count,cited_by_count",
        "per-page": limit,
    })
    url = f"{OPENALEX_API}/{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        return {"error": f"search failed for {et!r}: {e}", "candidates": []}
    cands = [
        {"id": _short_id(x.get("id")), "display_name": x.get("display_name"),
         "hint": f"{x.get('works_count', 0)} works, {x.get('cited_by_count', 0)} citations"}
        for x in data.get("results", [])[:limit]
    ]
    return {"candidates": cands,
            "note": "ranked by relevance; prefer the FIRST candidate unless the request clearly points elsewhere"}


# ---------------------------------------------------------------------------
# The agentic loop
# ---------------------------------------------------------------------------
def _api_key():
    return os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


def nl_to_oqo(question, model=DEFAULT_MODEL, registry=None, max_tokens=1500, verbose=False):
    """Run NL → OQO. Returns a dict:
       {oqo, canonical_oqo, validation, usage, deciding... , error, raw_oqo}
    `oqo`/`canonical_oqo` are dicts (canonical), or None on failure (error set)."""
    import anthropic

    key = _api_key()
    if not key:
        raise RuntimeError("set CLAUDE_API_KEY (or ANTHROPIC_API_KEY)")
    client = anthropic.Anthropic(api_key=key)

    if registry is None:
        registry = load_registry()
    system_blocks = build_system_blocks(registry)

    messages = [{"role": "user", "content": f"Request: {question}"}]
    usage_totals = {"input_tokens": 0, "output_tokens": 0,
                    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    n_resolves = 0

    def _accum(u):
        usage_totals["input_tokens"] += getattr(u, "input_tokens", 0) or 0
        usage_totals["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        usage_totals["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
        usage_totals["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0

    for _turn in range(MAX_TOOL_TURNS):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=TOOLS,
            tool_choice={"type": "any"},  # force a tool call every turn (no bare prose)
            messages=messages,
        )
        _accum(resp.usage)

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            # model didn't call a tool — nudge once via an error, else give up
            return _fail("model did not call a tool", question, usage_totals, n_resolves)

        # record the assistant turn
        messages.append({"role": "assistant", "content": resp.content})

        # cannot_translate ends the loop with a structured refusal (e.g. a
        # collection reference — out of NL v1 scope, decision 4).
        refuse = next((t for t in tool_uses if t.name == "cannot_translate"), None)
        if refuse:
            reason = refuse.input.get("reason", "unspecified")
            res = _fail(f"cannot_translate: {reason}", question, usage_totals, n_resolves)
            res["refused"] = True
            return res

        # submit_oqo ends the loop
        submit = next((t for t in tool_uses if t.name == "submit_oqo"), None)
        if submit:
            raw = submit.input.get("oqo")
            return _finalize(raw, question, usage_totals, n_resolves, verbose)

        # otherwise service resolve_entity calls
        tool_results = []
        for t in tool_uses:
            if t.name == "resolve_entity":
                n_resolves += 1
                res = resolve_entity_call(t.input.get("entity_type", ""), t.input.get("query", ""))
                if verbose:
                    print(f"  resolve_entity({t.input}) -> {res}")
            else:
                res = {"error": f"unknown tool {t.name}"}
            tool_results.append({"type": "tool_result", "tool_use_id": t.id,
                                 "content": json.dumps(res)})
        messages.append({"role": "user", "content": tool_results})

    return _fail("exceeded max tool turns", question, usage_totals, n_resolves)


def _finalize(raw_oqo, question, usage, n_resolves, verbose=False):
    result = {"question": question, "raw_oqo": raw_oqo, "oqo": None,
              "canonical_oqo": None, "validation": None, "usage": usage,
              "n_resolves": n_resolves, "error": None}
    if not isinstance(raw_oqo, dict):
        result["error"] = "submit_oqo did not return an object"
        return result
    try:
        oqo = OQO.from_dict(raw_oqo)
    except Exception as e:
        result["error"] = f"OQO parse error: {e}"
        return result
    vr = validate_oqo(oqo)
    result["validation"] = vr.to_dict()
    if not (vr.is_valid if hasattr(vr, "is_valid") else vr.to_dict().get("valid")):
        result["error"] = "OQO failed validation"
        result["oqo"] = oqo.to_dict()
        return result
    canon = canonicalize_oqo(oqo)
    result["oqo"] = canon.to_dict()
    result["canonical_oqo"] = canon.to_dict()
    if verbose:
        print("  OQO:", json.dumps(canon.to_dict()))
    return result


def _fail(msg, question, usage, n_resolves):
    return {"question": question, "raw_oqo": None, "oqo": None, "canonical_oqo": None,
            "validation": None, "usage": usage, "n_resolves": n_resolves, "error": msg}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "open access papers from Harvard published since 2020"
    out = nl_to_oqo(q, verbose=True)
    print(json.dumps({k: v for k, v in out.items() if k != "raw_oqo"}, indent=2, default=str))
