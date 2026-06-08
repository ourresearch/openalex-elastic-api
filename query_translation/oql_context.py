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
_DIRECTIVE_WORDS = {"where", "sort", "group", "sample"}

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
            for w in ("where", "sort by", "group by", "sample")]


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
        return {"category": CONNECTIVE,
                "suggestions": [{"value": "and", "kind": "connective"},
                                {"value": "or", "kind": "connective"}]}
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
    if cov is not None and cov.kind in ("STRING", "ANNOT"):
        return _suppressed(_leading_entity(q), diagnostic)  # literal text / inert
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
    ctx = _shape(raw)
    ctx["prefix"] = prefix
    ctx["replace_range"] = replace
    # widen the replace range backwards across a partially-typed multi-word field
    if ctx["category"] == FIELD and prefix:
        _extend_multiword_prefix(prior, ctx, replace)
    return {"entity": raw.get("entity"), "context": ctx,
            "diagnostic": _diag(diagnostic) if diagnostic else None}


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
