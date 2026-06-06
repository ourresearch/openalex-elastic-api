"""Cursor-position → grammar-state resolver for the IDE-style OQL editor (oxjob #357).

Given an OQL string and a cursor offset, answer: *what grammar element is expected
here?* — a field name? an operator? an entity-value (and which entity type)? a
connective? a directive keyword? — so the editor can show the right autocomplete.

This is the editor counterpart to the parser. The production parser
(`oql_lang._Parser`) is a strict, fail-fast recognizer — almost every method raises
`OQLError` on the first incomplete token, which is exactly the state an in-progress
query is always in. So we do NOT reuse `_Parser`; instead we mirror its greedy
field/operator matchers (`_parse_field`, `_parse_operator`, `_starts_new_clause`) in a
lightweight, non-raising token walker that classifies the trailing context.

Pure module: imports only the lexer + registry from `oql_lang` (no Flask / ES / DB), so
it is unit-testable under the `.venv-oql` venv with `PYTHONPATH=.`. The HTTP route layer
(`query_translation/views.py`) enriches the result with the authoritative full
suggestion lists from `/properties`; here we use the focused `oql_lang._FIELDS` registry
that the grammar itself uses.
"""
from typing import List, Optional, Tuple, Dict, Any

from query_translation.oql_lang import (
    lex, Tok, OQLError, Field,
    _ALIAS, _FIELDS, ENTITY_TYPES, _CONNECTIVES,
)

# --- grammar-state categories -------------------------------------------------
ENTITY = "entity"
FIELD = "field"
OPERATOR = "operator"
VALUE = "value"
CONNECTIVE = "connective"
DIRECTIVE = "directive-keyword"
END = "annotation-or-end"
NONE = "none"

# Bool-clause openers ("it's open access") and directive keywords.
_BOOL_OPENERS = {"it's", "its", "it"}
_DIRECTIVE_WORDS = {"where", "sort", "group", "sample"}

# Operators offered per field kind, in canonical OQL spelling (mirrors the shapes
# `_parse_operator` accepts; `within N words` / `near "..."` are search-value modes).
KIND_OPERATORS: Dict[str, List[str]] = {
    "search": ["contains", "does not contain", "near", "is similar to"],
    "bool":   [],  # surfaced via the "it's ..." phrasings instead
    "num":    ["is", "is not", ">", ">=", "<", "<=", "is unknown"],
    "id":     ["is", "is not", "is any of", "is not any of", "is in", "is unknown"],
    "enum":   ["is", "is not", "is any of", "is not any of", "is in", "is unknown"],
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


# --- token-span helpers -------------------------------------------------------
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


# --- greedy matchers (non-raising mirrors of _Parser) -------------------------
def _match_field(toks: List[Tok], i: int) -> Optional[Tuple[str, Field, int]]:
    """Greedy longest field-alias match (up to 4 words), mirroring
    oql_lang._parse_field. Returns (spelling, Field, n_tokens) or None."""
    best, best_len = None, 0
    parts: List[str] = []
    for k in range(4):
        t = toks[i + k] if i + k < len(toks) else None
        if not t or t.kind != "WORD":
            break
        parts.append(t.val)
        if " ".join(parts).lower() in _ALIAS:
            best, best_len = _ALIAS[" ".join(parts).lower()], k + 1
    if best is None:
        return None
    spelling = " ".join(toks[i + k].val for k in range(best_len))
    return spelling, best, best_len


def _word(toks: List[Tok], i: int) -> Optional[str]:
    t = toks[i] if 0 <= i < len(toks) else None
    return t.val.lower() if t and t.kind == "WORD" else None


def _match_operator(toks: List[Tok], i: int) -> Optional[Tuple[str, int, bool, bool]]:
    """Greedy operator match mirroring oql_lang._parse_operator.
    Returns (op, n_tokens, complete, opens_list) or None if the next token can't
    begin an operator. `complete=False` means a multi-word operator is still being
    typed (e.g. `is any` without `of`). `opens_list` is True for in/nin/any-of."""
    if i >= len(toks):
        return None
    t = toks[i]
    if t.kind == "OP":  # > >= < <=
        return t.val, 1, True, False
    w = _word(toks, i)
    if w == "contains":
        return "contains", 1, True, False
    if w == "is":
        n1 = _word(toks, i + 1)
        if n1 == "similar":
            if _word(toks, i + 2) == "to":
                return "similar", 3, True, False
            return "similar", 2, False, False  # `is similar` — still typing
        if n1 == "not":
            n2 = _word(toks, i + 2)
            if n2 == "any":
                if _word(toks, i + 3) == "of":
                    return "nin", 4, True, True
                return "nin", 3, False, True   # `is not any` — typing
            if n2 == "in":
                return "nin", 3, True, True
            return "isnot", 2, True, False     # `is not` (scalar)
        if n1 == "any":
            if _word(toks, i + 2) == "of":
                return "in", 3, True, True
            return "in", 2, False, True        # `is any` — typing
        if n1 == "in":
            return "in", 2, True, True
        return "is", 1, True, False
    if w in ("does", "doesn't", "doesnt"):
        j = i + 1
        if _word(toks, j) == "not":
            j += 1
        if _word(toks, j) == "contain":
            return "ncontains", j - i + 1, True, False
        return "ncontains", j - i, False, False  # `does not` — typing
    return None


# --- value-list / paren analysis ---------------------------------------------
def _unclosed_lp_index(toks: List[Tok]) -> Optional[int]:
    """Index of the last unmatched '(' in `toks`, else None."""
    stack: List[int] = []
    for idx, t in enumerate(toks):
        if t.kind == "LP":
            stack.append(idx)
        elif t.kind == "RP" and stack:
            stack.pop()
    return stack[-1] if stack else None


def _current_clause_start(toks: List[Tok]) -> int:
    """Index where the clause containing the cursor begins: just after the last
    top-level (depth-0) connective at the END of `toks`. (Paren/list handling is
    done by the caller before this is reached.)"""
    depth = 0
    for idx in range(len(toks) - 1, -1, -1):
        t = toks[idx]
        if t.kind == "RP":
            depth += 1
        elif t.kind == "LP":
            depth -= 1
        elif depth == 0 and t.kind == "WORD" and t.val.lower() in _CONNECTIVES:
            return idx + 1
    return 0


# --- response builders --------------------------------------------------------
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

    # (C) classify
    ctx = _classify(prior)
    ctx["prefix"] = prefix
    ctx["replace_range"] = replace
    # widen the replace range backwards across a partially-typed multi-word field
    if ctx["category"] == FIELD and prefix:
        _extend_multiword_prefix(prior, ctx, replace)
    return {"entity": _consumed_entity(prior), "context": ctx,
            "diagnostic": _diag(diagnostic) if diagnostic else None}


def _classify(prior: List[Tok]) -> Dict[str, Any]:
    # strip trailing inert annotations
    p = list(prior)
    while p and p[-1].kind == "ANNOT":
        p.pop()
    # SEMI resets to a fresh statement segment
    if p and p[-1].kind == "SEMI":
        return {"category": DIRECTIVE,
                "suggestions": [{"value": w, "kind": "directive"}
                                for w in ("where", "sort by", "group by", "sample")]}
    if any(t.kind == "SEMI" for t in p):
        last_semi = max(i for i, t in enumerate(p) if t.kind == "SEMI")
        p = p[last_semi + 1:]

    if not p:
        return {"category": ENTITY, "suggestions": _entity_suggestions("")}

    entity, rest = _consume_entity_tokens(p)
    if entity is None:
        # first word isn't (yet) a known entity — still the entity slot
        return {"category": ENTITY, "suggestions": _entity_suggestions("")}

    if not rest:
        return {"category": DIRECTIVE,
                "suggestions": [{"value": w, "kind": "directive"}
                                for w in ("where", "sort by", "group by", "sample")]}

    head = rest[0].val.lower() if rest[0].kind == "WORD" else None
    if head == "where":
        return _classify_conditions(rest[1:])
    if head in ("sort", "group"):
        # after "sort by" / "group by" -> a (sortable/groupable) field name
        body = rest[2:] if (len(rest) > 1 and rest[1].kind == "WORD"
                            and rest[1].val.lower() == "by") else rest[1:]
        # between keys, a comma or asc/desc may intervene; offer field names
        return {"category": FIELD, "suggestions": _field_suggestions(),
                "directive": head}
    if head == "sample":
        return {"category": VALUE, "value_kind": "num", "field": "sample",
                "operators": [], "autocomplete_entity": None, "suggestions": []}
    # entity present, trailing junk -> offer directives/end
    return {"category": END,
            "suggestions": [{"value": w, "kind": "directive"}
                            for w in ("where", "sort by", "group by", "sample")]}


def _classify_conditions(cond: List[Tok]) -> Dict[str, Any]:
    """Classify the cursor's position within the `where`-conditions tokens."""
    if not cond:
        return {"category": FIELD, "suggestions": _field_suggestions()}

    # value-list / boolean-group: is the cursor inside an unmatched '(' ?
    lp = _unclosed_lp_index(cond)
    if lp is not None:
        before_lp = cond[:lp]
        # what governs this paren? the operator immediately before it.
        gov = _governing_list_field(before_lp)
        inside = cond[lp + 1:]
        if gov is not None and not _has_value_after_comma_boundary(inside):
            # inside a value list: each comma-separated slot expects a value
            return _value_context(VALUE, gov, in_list=True)
        if gov is not None:
            return _value_context(VALUE, gov, in_list=True)
        # boolean group: a fresh sub-expression begins after '('
        return _classify_conditions(inside)

    # not in a paren: take the trailing clause
    clause = cond[_current_clause_start(cond):]
    return _classify_clause(clause)


def _governing_list_field(before_lp: List[Tok]) -> Optional[Field]:
    """If the tokens right before an open '(' end in a value-list operator
    (is any of / is not any of / is in), return the Field being listed; else None
    (the '(' is a boolean group)."""
    fm = None
    # find the last field+operator pair ending at before_lp's tail
    start = _current_clause_start(before_lp)
    clause = before_lp[start:]
    m = _match_field(clause, 0)
    if not m:
        return None
    _spelling, fld, flen = m
    op = _match_operator(clause, flen)
    if op and op[2] and op[3]:  # complete & opens_list
        return fld
    return None


def _has_value_after_comma_boundary(inside: List[Tok]) -> bool:
    # placeholder hook for finer in-list cursor logic; always treat as value slot
    return False


def _classify_clause(clause: List[Tok]) -> Dict[str, Any]:
    if not clause:
        return {"category": FIELD, "suggestions": _field_suggestions()}

    # boolean "it's ..." clause
    if clause[0].kind == "WORD" and clause[0].val.lower() in _BOOL_OPENERS:
        return {"category": VALUE, "value_kind": "bool", "field": "it's",
                "operators": [], "autocomplete_entity": None,
                "suggestions": _bool_phrase_suggestions()}

    m = _match_field(clause, 0)
    if m is None:
        return {"category": FIELD, "suggestions": _field_suggestions()}
    _spelling, fld, flen = m
    rest = clause[flen:]
    if not rest:
        return {"category": OPERATOR, "field": fld.oql, "value_kind": fld.kind,
                "operators": KIND_OPERATORS.get(fld.kind, []),
                "suggestions": [{"value": o, "kind": "operator"}
                                for o in KIND_OPERATORS.get(fld.kind, [])]}

    op = _match_operator(rest, 0)
    if op is None or not op[2]:
        # still typing the operator (or unknown token where an op is expected)
        return {"category": OPERATOR, "field": fld.oql, "value_kind": fld.kind,
                "operators": KIND_OPERATORS.get(fld.kind, []),
                "suggestions": [{"value": o, "kind": "operator"}
                                for o in KIND_OPERATORS.get(fld.kind, [])]}
    _opstr, olen, _complete, opens_list = op
    after = rest[olen:]
    # a value present after the operator -> we're past the value: connective/end
    has_value = any(t.kind in ("WORD", "STRING") for t in after)
    if has_value:
        return {"category": CONNECTIVE,
                "suggestions": [{"value": "and", "kind": "connective"},
                                {"value": "or", "kind": "connective"}]}
    # no value yet -> expect a value of the field's kind
    return _value_context(VALUE, fld, in_list=opens_list)


# --- entity helpers -----------------------------------------------------------
def _consume_entity_tokens(toks: List[Tok]) -> Tuple[Optional[str], List[Tok]]:
    """Mirror _parse_entity's greedy 2-then-1 word match. Returns (entity, rest)."""
    if not toks or toks[0].kind != "WORD":
        return None, toks
    if len(toks) > 1 and toks[1].kind == "WORD":
        two = f"{toks[0].val} {toks[1].val}".lower()
        if two in ENTITY_TYPES:
            return two, toks[2:]
    one = toks[0].val.lower()
    if one in ENTITY_TYPES:
        return one, toks[1:]
    return None, toks


def _consumed_entity(prior: List[Tok]) -> Optional[str]:
    p = [t for t in prior if t.kind != "ANNOT"]
    entity, _ = _consume_entity_tokens(p)
    return entity


def _leading_entity(q: str) -> Optional[str]:
    try:
        return _consumed_entity(lex(q))
    except OQLError:
        try:
            first = q.strip().split()[0].lower()
            return first if first in ENTITY_TYPES else None
        except IndexError:
            return None


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
