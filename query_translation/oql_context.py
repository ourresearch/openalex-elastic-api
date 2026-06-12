"""Cursor-position → grammar-state resolver for the IDE-style OQL editor (oxjob #357).

Given an OQL string and a cursor offset, answer: *what grammar element is expected
here?* — a field name? an operator? an entity-value (and which entity type)? a
connective? a directive keyword? — so the editor can show the right autocomplete.

**Single source of grammar truth (oxjob #363, charter decision 15).** This module no
longer re-implements the grammar. It does two framework-independent jobs —

  1. **cursor geometry** — defensively lex, find the token under the cursor, derive the
     replacement `prefix` + `replace_range`, and the `prior` tokens before the cursor;
  2. **presentation** — turn the engine's reported grammar-state category into concrete
     suggestion lists from the OQL field registry —

and delegates the actual *"what does the grammar expect at the cursor?"* question to the
production parser running in **context mode** (`oql_lang._Parser.parse_for_context`). The
old parallel token-walker (`_classify*`, paren/clause analysis, entity-consume) has been
**retired**: it was a second encoding of the grammar that could drift from `_Parser`, and
since the parser is the thing that ultimately accepts or rejects a query, the editor must
agree with it by construction. (The field/operator matchers were already shared in part 1
of the #386 pair; this retires the last parallel piece — grammar-state classification.)

Pure module: imports only the lexer + parser + registry from `oql_lang` (no Flask / ES /
DB), so it is unit-testable under the OQL venv with `PYTHONPATH=.`. The HTTP route layer
(`query_translation/editor_views.py`) wraps `parse_context`; the engine's own `_FIELDS`
registry (everything the grammar will actually parse) is the suggestion vocabulary, so the
editor never offers a field the parser would then reject.
"""
from typing import List, Optional, Dict, Any

from query_translation.oql_lang import (
    lex, Tok, OQLError, Field, _Parser,
    _ALIAS, _FIELDS, ENTITY_TYPES, _CONNECTIVES,
    match_field, match_operator,
    CTX_ENTITY, CTX_FIELD, CTX_OPERATOR, CTX_VALUE, CTX_CONNECTIVE,
    CTX_DIRECTIVE, CTX_END, CTX_NONE,
)

# The field/operator matchers are SHARED with the production parser (oxjob #363) — aliased
# to the historical private names the tests below already use.
_match_field = match_field
_match_operator = match_operator

# --- grammar-state categories (re-exported from the engine — single source) ---------
ENTITY = CTX_ENTITY
FIELD = CTX_FIELD
OPERATOR = CTX_OPERATOR
VALUE = CTX_VALUE
CONNECTIVE = CTX_CONNECTIVE
DIRECTIVE = CTX_DIRECTIVE
END = CTX_END
NONE = CTX_NONE

# Directive words that bound a partially-typed multi-word field alias when widening
# the replace-range backwards.
_DIRECTIVE_WORDS = {"where", "sort", "group", "sample", "return"}

# Sort-direction words (canonical first — the suggestion list offers asc/desc only).
_DIRECTIONS = ("asc", "desc", "ascending", "descending")

# Operators offered per field kind, in canonical OQL spelling (mirrors the shapes
# `match_operator` accepts; `within N words` / `near "..."` are search-value modes).
KIND_OPERATORS: Dict[str, List[str]] = {
    "search": ["contains", "does not contain", "near", "is similar to"],
    "bool":   [],  # surfaced via the "it's ..." phrasings instead
    "num":    ["is", "is not", ">", ">=", "<", "<=", "is unknown"],
    # lists are written with parentheses now (#363): `is (a or b)` — the `any of`/
    # `is in` list keywords were removed, so they're no longer suggested.
    "id":     ["is", "is not", "is unknown"],
    "enum":   ["is", "is not", "is unknown"],
    "string": ["is", "is not", "is unknown"],
}

# id-kind column_id -> the entity type whose /autocomplete/{entity} resolves its values.
# Subset of core/fields.py:ENTITY_ID_PARAM_TYPES covering the columns the OQL grammar
# exposes (hardcoded here to keep this module pure / Flask-free). Columns with no live
# /autocomplete route (sdgs/domains/fields) still return the semantic entity; the editor
# falls back to enum/free-text when the route 404s or is empty.
_COLUMN_AUTOCOMPLETE_ENTITY: Dict[str, str] = {
    "authorships.institutions.lineage": "institutions",
    "last_known_institutions.id": "institutions",
    "authorships.author.id": "authors",
    "primary_location.source.id": "sources",
    "primary_topic.id": "topics",
    "topics.id": "topics",
    "funders.id": "funders",
    "sustainable_development_goals.id": "sdgs",
    "domain.id": "domains",
    "primary_topic.field.id": "fields",
    # ids.openalex (the work's own id) intentionally absent -> null (free text).
}


# --- token-span helpers (cursor geometry) ------------------------------------
def _tok_raw_len(t: Tok) -> int:
    """Length of the token's raw source text (Tok.val is the *inner* text for
    STRING/ANNOT, so add the two delimiter chars)."""
    if t.kind in ("STRING", "ANNOT"):
        return len(t.val) + 2
    if t.kind in ("LP", "RP", "COMMA", "SEMI"):
        return 1
    return len(t.val)  # WORD, OP


def _tok_end(t: Tok) -> int:
    return t.pos + _tok_raw_len(t)


def _covering(toks: List[Tok], cpos: int):
    """Return (index, tok) of the token the cursor sits within, else (None, None).

    WORD/OP: a cursor at the end-of-token counts (a word being typed). STRING/ANNOT:
    only *strictly inside* counts (cursor right after the closing quote/bracket is
    'after'). Bare punctuation (LP/RP/COMMA/SEMI) is never 'inside'."""
    for idx, t in enumerate(toks):
        start, end = t.pos, _tok_end(t)
        if t.kind in ("WORD", "OP"):
            if start <= cpos <= end:
                return idx, t
        elif t.kind in ("STRING", "ANNOT"):
            if start < cpos < end:
                return idx, t
    return None, None


# --- response builders (presentation) ----------------------------------------
def _suppressed(entity, diagnostic=None) -> Dict[str, Any]:
    ctx = {"category": NONE, "prefix": "", "replace_range": None}
    return {"entity": entity, "context": ctx,
            "diagnostic": _diag(diagnostic) if diagnostic else None}


def _diag(e: OQLError) -> Dict[str, Any]:
    return {"code": e.code, "message": e.message, "fixit": e.fixit,
            "position": e.position}


def _entity_suggestions(prefix: str) -> List[Dict[str, str]]:
    return [{"value": e, "kind": "entity"} for e in sorted(ENTITY_TYPES)]


def _field_suggestions() -> List[Dict[str, str]]:
    """Canonical field spellings + the bool 'it's ...' openers (from _FIELDS)."""
    out, seen = [], set()
    for _spellings, fld in _FIELDS:
        if fld.oql not in seen:
            seen.add(fld.oql)
            out.append({"value": fld.oql, "kind": "field"})
    for _spellings, fld in _FIELDS:
        if fld.kind == "bool" and fld.bool_true:
            out.append({"value": fld.bool_true, "kind": "bool-phrase"})
    return out


def _bool_phrase_suggestions() -> List[Dict[str, str]]:
    out = []
    for _spellings, fld in _FIELDS:
        if fld.kind == "bool":
            # the phrase tail after "it's"/"it" — e.g. "open access", "retracted"
            if fld.bool_true:
                tail = fld.bool_true
                for pre in ("it's ", "it "):
                    if tail.startswith(pre):
                        tail = tail[len(pre):]
                        break
                out.append({"value": tail, "kind": "bool-phrase"})
    return out


def _value_context(category, fld: Field, in_list=False) -> Dict[str, Any]:
    ctx = {
        "category": category,
        "value_kind": fld.kind,
        "field": fld.oql,
        "column": fld.column,  # lets the route map enum columns -> config vocab (#357)
        "operators": KIND_OPERATORS.get(fld.kind, []),
        "in_list": in_list,
        "autocomplete_entity": None,
        "suggestions": [],
    }
    if fld.kind == "id":
        ctx["autocomplete_entity"] = _COLUMN_AUTOCOMPLETE_ENTITY.get(fld.column)
    if fld.kind in ("num", "id", "enum", "string"):
        ctx["suggestions"] = [{"value": "unknown", "kind": "value-keyword"}]
    return ctx


def _directive_suggestions() -> List[Dict[str, str]]:
    return [{"value": w, "kind": "directive"}
            for w in ("where", "sort by", "group by", "sample", "return")]


def _shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Turn the engine's reported (category + Field/payload) into the editor's
    context dict (concrete suggestion lists, value_kind, autocomplete_entity)."""
    cat = raw["category"]
    if cat == ENTITY:
        return {"category": ENTITY, "suggestions": _entity_suggestions("")}
    if cat == FIELD:
        out = {"category": FIELD, "suggestions": _field_suggestions()}
        if raw.get("directive"):
            out["directive"] = raw["directive"]
        # Post-connective FIELD slot (cursor right after `... or`/`and`): carry the
        # sibling clause so the editor's sectioned menu can offer "add another value
        # to this filter" (auto-paren rewrite) alongside "start a new filter" (#357).
        # Char ranges (sibling.clause_range / value_range) are filled in by
        # parse_context, which has the token list; here we just thread the connective
        # + the sibling field's identity. Only for a bare `field op value` sibling.
        if raw.get("after_connective"):
            out["after_connective"] = raw["after_connective"]
            sfld = raw.get("sibling_fld")
            if raw.get("sibling_simple") and sfld is not None \
                    and raw.get("sibling_value_start") is not None:
                sib = {
                    "field": sfld.oql,
                    "column": sfld.column,
                    "value_kind": sfld.kind,
                    # token indices (into the prefix token list) — converted to char
                    # offsets by parse_context; dropped from the final reply.
                    "_clause_span": raw.get("sibling_clause_span"),
                    "_value_start_i": raw.get("sibling_value_start"),
                }
                # id sibling -> the entity whose /autocomplete/{entity} resolves "add
                # another value" (institutions, authors, …). Lets the editor offer a
                # live entity lookup in the sectioned menu, not just static enum vocab
                # (#357 iter-3 — multi-value id filters). Enum siblings get their config
                # vocab attached by the route's _enrich_enum_suggestions instead.
                if sfld.kind == "id":
                    sib["autocomplete_entity"] = \
                        _COLUMN_AUTOCOMPLETE_ENTITY.get(sfld.column)
                out["sibling"] = sib
        return out
    if cat == OPERATOR:
        fld = raw.get("fld")
        kind = fld.kind if fld is not None else None
        ops = KIND_OPERATORS.get(kind, [])
        return {"category": OPERATOR, "field": fld.oql if fld is not None else None,
                "value_kind": kind, "operators": ops,
                "suggestions": [{"value": o, "kind": "operator"} for o in ops]}
    if cat == VALUE:
        fld = raw.get("fld")
        if fld is not None:
            return _value_context(VALUE, fld, in_list=raw.get("in_list", False))
        kind = raw.get("kind")
        if kind == "bool":
            return {"category": VALUE, "value_kind": "bool", "field": "it's",
                    "operators": [], "autocomplete_entity": None,
                    "suggestions": _bool_phrase_suggestions()}
        # kind-only value slot (e.g. `sample N`)
        return {"category": VALUE, "value_kind": kind, "field": raw.get("field"),
                "operators": [], "autocomplete_entity": None, "suggestions": []}
    if cat == CONNECTIVE:
        # The cursor sits after a complete clause. The grammar accepts a connective
        # (continue the where-expr) OR a trailing directive (sort/group/sample) OR
        # end. Offer all of them so the editor's "menu 1" is the full two-level
        # design's first level (oxjob #357): and / or / sort by / group by /
        # sample / return.
        # (`where` is NOT re-offered — we're already inside the where-expression.)
        return {"category": CONNECTIVE,
                "suggestions": [{"value": "and", "kind": "connective"},
                                {"value": "or", "kind": "connective"}]
                               + [{"value": w, "kind": "directive"}
                                  for w in ("sort by", "group by", "sample",
                                            "return")]}
    if cat in (DIRECTIVE, END):
        return {"category": cat, "suggestions": _directive_suggestions()}
    # NONE / unclassifiable
    return {"category": NONE}


# --- engine-backed classification --------------------------------------------
def _classify_via_engine(prior: List[Tok]) -> Dict[str, Any]:
    """Run the production parser over the `prior` tokens in context mode and return
    its raw grammar-state report ({category, entity, **payload})."""
    return _Parser(list(prior)).parse_for_context()


def _leading_entity(q: str) -> Optional[str]:
    """Best-effort entity for the suppressed (inside string/annotation) replies."""
    try:
        toks = lex(q)
    except OQLError:
        try:
            first = q.strip().split()[0].lower()
            return first if first in ENTITY_TYPES else None
        except IndexError:
            return None
    return _classify_via_engine(toks).get("entity")


# --- main entry ---------------------------------------------------------------
def parse_context(q: str, pos: Optional[int] = None) -> Dict[str, Any]:
    """Resolve the grammar context at `pos` (code-point offset) in OQL string `q`."""
    if pos is None:
        pos = len(q)
    cpos = max(0, min(pos, len(q)))

    # (A) lex defensively. Unterminated string/annotation: suppress if the cursor is
    # inside/after the broken token; otherwise classify against the clean prefix.
    diagnostic = None
    try:
        toks = lex(q)
    except OQLError as e:
        if e.position is not None and cpos > e.position:
            return _suppressed(_leading_entity(q), e)
        diagnostic = e
        try:
            toks = lex(q[:cpos])
        except OQLError:
            return _suppressed(None, e)

    # (B) locate the token under the cursor -> prefix + replace_range + `prior`.
    idx, cov = _covering(toks, cpos)
    if cov is not None and cov.kind == "STRING":
        return _suppressed(_leading_entity(q), diagnostic)  # literal search text
    if cov is not None and cov.kind == "ANNOT":
        # Annotation click (#357 iter-5): `[Name]` decorates the value right before it,
        # so a cursor inside the brackets re-anchors to that value token — the editor
        # then shows the entity-swap menu instead of a dead spot. (Strings stay
        # suppressed above: they're literal search text, not a grammar slot.)
        if idx > 0 and toks[idx - 1].kind == "WORD":
            idx, cov = idx - 1, toks[idx - 1]
        else:
            return _suppressed(_leading_entity(q), diagnostic)
    if cov is not None and cov.kind == "WORD":
        prefix = cov.val[: cpos - cov.pos]
        replace = {"start": cov.pos, "end": _tok_end(cov)}
        prior = toks[:idx]
    else:
        prefix = ""
        replace = {"start": cpos, "end": cpos}
        prior = [t for t in toks if _tok_end(t) <= cpos]

    # (C) classify via the production parser (single source of grammar truth)
    raw = _classify_via_engine(prior)
    # Multiword-VALUE widening (#357 iter-3 bug 1): if the cursor word is the tail of a
    # partially-typed multi-word value (`institution is university of fl`, `country is
    # united ki`), strict classification of the full prefix mis-reads the first value
    # word as a *complete* value and reports the cursor as a connective/none slot. Re-run
    # the parser against just `field <operator>` so we get the VALUE context back, then
    # widen the prefix + replace_range across the value words already typed.
    widened = None
    if prefix:
        widened = _widen_multiword_value(prior, prefix)
        # Post-connective value widening only when the normal parse is UNUSABLE (NONE):
        # if the trailing text classifies as a partial field (`… and last known inst`)
        # or a real new clause (`… and last known institution is har`), that wins — only
        # genuinely un-fieldlike trailing words (a bare multi-word entity/enum name) are
        # treated as 'another value' (oxjob #357 iter-3).
        if widened is None and raw.get("category") == NONE:
            widened = _widen_post_connective_value(prior, prefix)
    if widened is not None:
        ctx, val_start = widened
        ctx["prefix"] = " ".join(t.val for t in prior[val_start:]) + " " + prefix
        replace["start"] = prior[val_start].pos
        ctx["replace_range"] = replace
    else:
        ctx = _shape(raw)
        ctx["prefix"] = prefix
        ctx["replace_range"] = replace
        # widen the replace range backwards across a partially-typed multi-word field
        if ctx["category"] == FIELD and prefix:
            _extend_multiword_prefix(prior, ctx, replace)
        # sort-direction slot (#357 iter-5): after `sort by <column>` the grammar also
        # accepts asc/desc, but the engine's END/DIRECTIVE report doesn't surface it —
        # so a click on `desc` had no menu. On a direction word, the slot IS the
        # asc/desc choice; on the open slot after the column, direction joins the list.
        _apply_direction_slot(q, prior, ctx, replace)
    # resolve the sibling clause's token-index spans into char offsets (#357)
    if ctx.get("sibling"):
        _resolve_sibling_ranges(prior, ctx["sibling"])
    return {"entity": raw.get("entity"), "context": ctx,
            "diagnostic": _diag(diagnostic) if diagnostic else None}


def _resolve_sibling_ranges(prior: List[Tok], sib: Dict[str, Any]) -> None:
    """Convert the sibling clause's token-index spans (recorded by the parser) into
    char offsets the editor can splice on — `clause_range` (the whole `field op
    value`) and `value_range` (just the existing value/list). Used by the sectioned
    menu's "add another value" auto-paren rewrite (oxjob #357). The leading-underscore
    index keys are internal; they're dropped here so the reply carries only offsets."""
    span = sib.pop("_clause_span", None)
    vstart_i = sib.pop("_value_start_i", None)
    if not span:
        return
    s_i, e_i = span
    if not (0 <= s_i < e_i <= len(prior)):
        return
    sib["clause_range"] = {"start": prior[s_i].pos, "end": _tok_end(prior[e_i - 1])}
    if vstart_i is not None and s_i <= vstart_i < e_i:
        sib["value_range"] = {"start": prior[vstart_i].pos,
                              "end": _tok_end(prior[e_i - 1])}


def _value_run_start(prior: List[Tok]) -> Optional[int]:
    """If `prior` ends with a partially-typed multi-token value (the words *after* a
    complete operator), return the index in `prior` where that value run begins; else
    None (oxjob #357 iter-3 bug 1).

    Found by locating the rightmost *complete* operator whose tokens-to-end form an
    unbroken run of value words (plain WORDs, no connective / paren / directive
    boundary). This reuses `match_operator` (shared grammar truth) rather than a
    hand-kept keyword stop-set, so the value/operator boundary can't drift from the
    parser — important because operator tails like `of`/`in` (`is any of`, `is in`)
    are also legal value words (`university of florida`). Single-token values — where
    the operator is the last `prior` token and the value's first word is the cursor
    word — return None; the normal path already classifies those correctly."""
    for i in range(len(prior) - 1, -1, -1):
        m = _match_operator(prior, i)
        if not m:
            continue
        _op, n, complete, _opens = m
        if not complete:
            continue
        val_start = i + n
        if val_start >= len(prior):
            return None  # operator is the last token; the value's 1st word IS the cursor
        run = prior[val_start:]
        if all(t.kind == "WORD" and t.val.lower() not in _CONNECTIVES for t in run) \
                and not any(_is_directive_boundary(run, j) for j in range(len(run))):
            return val_start
        return None
    return None


def _is_directive_boundary(run: List[Tok], j: int) -> bool:
    """True if run[j] starts a trailing directive (`sort by` / `group by` /
    `sample <N>` / `return` / `where`) rather than continuing a multi-word value.
    Without this a doc like `type is article sort by citation count de▮sc` widens
    the whole tail into one giant 'value' and the cursor never reaches the
    direction slot (oxjob #357 iter-5)."""
    t = run[j]
    if t.kind != "WORD":
        return False
    w = t.val.lower()
    if w in ("where", "return"):
        return True
    nxt = run[j + 1] if j + 1 < len(run) else None
    if w in ("sort", "group"):
        return nxt is not None and nxt.kind == "WORD" and nxt.val.lower() == "by"
    if w == "sample":
        return nxt is not None and nxt.kind == "WORD" and nxt.val.isdigit()
    return False


def _widen_multiword_value(prior: List[Tok], prefix: str):
    """If the cursor word continues a multi-word value, reclassify against `field
    <operator>` (the value run stripped off) so the parser reports the VALUE context.
    Returns `(shaped_ctx, value_run_start_index)` or None (oxjob #357 iter-3 bug 1)."""
    val_start = _value_run_start(prior)
    if val_start is None:
        return None
    raw = _classify_via_engine(prior[:val_start])
    if raw.get("category") != VALUE:
        return None
    return _shape(raw), val_start


def _widen_post_connective_value(prior: List[Tok], prefix: str):
    """If `prior` ends with `<connective> <words…>` where the trailing words are a
    partially-typed multi-word value for the *preceding* id/enum clause — the editor's
    'add another value' flow typed past the first word (`institution is <id> and
    university of fl`) — reclassify against the text up to and including the connective
    (which yields the after_connective FIELD context + the sibling) so the caller widens
    the prefix across the trailing words. Returns `(shaped_ctx, value_run_start_index)`
    or None.

    Without this the parser reads `university of` as a broken *new field* clause and
    degrades to NONE, so a multi-word second value never autocompletes. Restricted to
    id/enum siblings (the 'another value' sectioned-menu cases); other value kinds fall
    through (oxjob #357 iter-3 — multi-value id filters)."""
    n = 0
    for t in reversed(prior):
        if t.kind == "WORD" and t.val.lower() not in _CONNECTIVES:
            n += 1
        else:
            break
    if n == 0 or n >= len(prior):
        return None
    conn = prior[len(prior) - n - 1]
    if not (conn.kind == "WORD" and conn.val.lower() in _CONNECTIVES):
        return None
    val_start = len(prior) - n
    raw = _classify_via_engine(prior[:val_start])  # tokens end at the connective
    if raw.get("category") != FIELD or not raw.get("after_connective"):
        return None
    ctx = _shape(raw)
    sib = ctx.get("sibling")
    if not (sib and sib.get("value_kind") in ("id", "enum")):
        return None
    return ctx, val_start


def _direction_allowed(prior: List[Tok]) -> bool:
    """True when the cursor sits in the current `sort by` segment after >=1 column
    word with no direction word yet — i.e. exactly where the grammar accepts a
    direction (oxjob #357 iter-5)."""
    last_sort = None
    for i, t in enumerate(prior):
        if t.kind != "WORD":
            continue
        w = t.val.lower()
        if w == "sort" and i + 1 < len(prior) and prior[i + 1].kind == "WORD" \
                and prior[i + 1].val.lower() == "by":
            last_sort = i
        elif w in ("group", "sample", "where", "return") and last_sort is not None \
                and i > last_sort:
            last_sort = None  # a later directive ended the sort tail
    if last_sort is None:
        return False
    seg: List[Tok] = []
    for t in prior[last_sort + 2:]:
        if t.kind == "COMMA":
            seg = []  # multi-sort: only the current comma segment counts
        else:
            seg.append(t)
    if not seg or not all(t.kind == "WORD" for t in seg):
        return False
    return not any(t.val.lower() in _DIRECTIONS for t in seg)


def _apply_direction_slot(q: str, prior: List[Tok], ctx: Dict[str, Any],
                          replace: Dict[str, int]) -> None:
    """Surface the sort-direction choice the engine's report omits (#357 iter-5):
    mutate `ctx` when the cursor sits where `asc`/`desc` is legal."""
    if ctx.get("category") not in (DIRECTIVE, END):
        return
    if not _direction_allowed(prior):
        return
    dir_sugg = [{"value": "asc", "kind": "direction"},
                {"value": "desc", "kind": "direction"}]
    full_token = q[replace["start"]:replace["end"]].strip().lower()
    if full_token in _DIRECTIONS:
        # the cursor is ON a direction word: this slot is exactly the asc/desc choice
        ctx["category"] = "direction"
        ctx["suggestions"] = dir_sugg
    else:
        # open slot right after the sort column: direction is a legal next step too
        ctx["suggestions"] = dir_sugg + ctx.get("suggestions", [])


def _extend_multiword_prefix(prior: List[Tok], ctx: Dict[str, Any],
                             replace: Dict[str, int]) -> None:
    """When the cursor word is the tail of a partially-typed multi-word field
    alias (e.g. `last known inst|`), widen the prefix + replace range back over the
    leading words so the editor can match the full alias."""
    run = []
    for t in reversed(prior):
        if t.kind == "WORD" and t.val.lower() not in _CONNECTIVES \
                and t.val.lower() not in _DIRECTIVE_WORDS:
            run.append(t)
        else:
            break
    if not run:
        return
    run.reverse()
    # only extend if `run + prefix` is a prefix of some known multi-word alias
    typed = (" ".join(t.val for t in run) + " " + ctx["prefix"]).lower()
    if any(alias.startswith(typed) and " " in alias for alias in _ALIAS):
        replace["start"] = run[0].pos
        ctx["prefix"] = " ".join(t.val for t in run) + " " + ctx["prefix"]
