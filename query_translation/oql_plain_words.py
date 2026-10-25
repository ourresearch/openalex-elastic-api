"""Plain words inside an OQL statement (oxjob #1597, Jason 2026-10-20).

Jason: "the user could just add a snippet of natural language somewhere, and the parser
would figure out that this shouldn't be parsed as OQL, it should just be parsed as natural
language and sent to the natural language system as part of a prompt."

The parser stays the only judge of what OQL is (one grammar, never a second one): this
module never reads OQL itself. It asks the parser about variants of the statement:

1. A typo first. One word that isn't OQL, close to an OQL word, whose fix makes the
   statement read (`fundd by` -> `funded by`), is a typo: the editor offers the fix, and
   nothing goes to the model.
2. Otherwise the plain words are a run of words that, taken out, leaves a statement the
   parser reads (`get works about kelp since 2020 but only the open access ones` -> `but only
   the open access ones`; the rest is `get works about kelp since 2020`).
3. A run that is OQL being typed is not plain words: one OQL word on its own (`since` in
   `get works about kelp since`), or the start of an OQL phrase at the end (`most cit`).
4. No run found in time (or the statement doesn't start with `get`): the whole statement is
   plain words, and there is no rest.

Pure Python, no ES or DB. Words come from the editor's lexer (oql_core_context._tokens) and
the grammar's own word tables; parses are cached; the search stops at DEADLINE.
"""
from __future__ import annotations

import bisect
import difflib
import functools
import re
import time
from typing import Any, Dict, Optional

MAX_SPAN = 16        # longest run of plain words tried, in words
DEADLINE = 0.08      # seconds per statement; /validate runs on every keystroke
_SEPARATORS = ("C", "P")   # the lexer's comma and full-stop tokens
_VALUES = ("L", "PL", "G", "OG", "S", "OS")   # links, groups, quotes: things the parser reads


@functools.lru_cache(maxsize=4096)
def _parses(text: str) -> bool:
    from query_translation.oql_parser import parse_either
    try:
        parse_either(text)
        return True
    except Exception:  # noqa: BLE001 (any parse failure means "doesn't read")
        return False


@functools.lru_cache(maxsize=1)
def _vocab():
    """(every single word of the grammar, every phrase lowercased, the words a typo can be
    of): the editor's vocabulary (oql_core_context.VOCABULARY, built from oql_core's tables)
    plus the general form's words from the parser's own sets."""
    from query_translation import oql_lang as G
    from query_translation.oql_context import _DIRECTIVE_WORDS, KIND_OPERATORS
    from query_translation.oql_core_context import VOCABULARY
    phrases = tuple(sorted({p["value"].lower() for p in VOCABULARY}))
    general = [*_DIRECTIVE_WORDS, *G._SEARCH_RUN_RESERVED, *G._STEP_OPENERS, *G._BARE_STEP_VERBS,
               *G._COMPARE_STOPS, *G._THING_VERBS, *G.THING_VERBS.values(),
               *(op for ops in KIND_OPERATORS.values() for op in ops),
               "then", "each", "those"]     # step words the parser matches by regex
    words = {w for p in (*phrases, *general) for w in re.findall(r"[a-z][a-z'\-]*", p.lower())}
    typo_targets = tuple(sorted(w for w in words if w.isalpha() and len(w) >= 3))
    return frozenset(words), phrases, typo_targets


def _is_grammar(word: str) -> bool:
    return word.lower() in _vocab()[0]


@functools.lru_cache(maxsize=8192)
def _close(word: str) -> tuple:
    """Grammar words a typo of `word` could be, closest first (the validator's did-you-mean)."""
    return tuple(difflib.get_close_matches(word, _vocab()[2], n=3, cutoff=0.8))


def _tokens(q: str, offset: int = 0):
    """(kind, start, end) of each token, from the editor's own lexer."""
    from query_translation.oql_core_context import _tokens as lex
    return [(t.kind, t.start + offset, t.end + offset) for t in lex(q)]


def _typo(q: str, toks) -> Optional[Dict[str, Any]]:
    for kind, s, e in toks:
        word = q[s:e]
        if kind != "W" or len(word) < 3 or not word.isalpha() or _is_grammar(word):
            continue
        for cand in _close(word.lower()):
            if _parses(q[:s] + cand + q[e:]):
                return {"kind": "typo", "start": s, "end": e, "word": word, "fix": cand}
    return None


def _is_being_typed(text: str, at_end: bool) -> bool:
    """OQL being typed, not plain words: one grammar word on its own, or the start of a
    grammar phrase at the end of the statement."""
    words = text.split()
    if len(words) == 1 and _is_grammar(words[0]):
        return True
    low = " ".join(w.lower() for w in words)
    return at_end and any(p.startswith(low) for p in _vocab()[1])


def _without(q: str, start: int, end: int) -> str:
    """The statement with q[start:end] taken out, spaced as typed (no comma left dangling at
    the end)."""
    return re.sub(r"\s+([,.])", r"\1", " ".join((q[:start] + " " + q[end:]).split())).rstrip(",")


def _runs(q: str, toks, first: int):
    """(key, cut, shown) for every run of words at one level (the statement, or the inside of
    one group), from token `first` on: `cut` is the (start, end) taken out, `shown` the same
    without a comma or full stop at its edges. Key, lowest first: the OQL words the run takes
    out (a link, group, quote, number or grammar word costs 1); its length in words; whether a
    grammar keyword sits just before it (`canada since` in `from canada since 2020` would hand
    `from` the year); the rightmost (people add words after what they keep)."""
    def cost(kind, s, e):
        w = q[s:e]
        return int(kind in _VALUES or any(c.isdigit() for c in w) or (kind == "W" and _is_grammar(w)))
    pre, nwords, real = [0], [0], []
    for k, (kind, s, e) in enumerate(toks):
        pre.append(pre[-1] + cost(kind, s, e))
        nwords.append(nwords[-1] + (kind not in _SEPARATORS))
        if kind not in _SEPARATORS:
            real.append(k)
    for i in range(first, len(toks)):
        before = toks[i - 1] if i > 0 else None
        kw = int(before is not None and before[0] == "W" and _is_grammar(q[before[1]:before[2]]))
        for j in range(i + 1, len(toks) + 1):
            n = nwords[j] - nwords[i]
            if n > MAX_SPAN:
                break
            if n == 0:
                continue
            a, b = real[bisect.bisect_left(real, i)], real[bisect.bisect_left(real, j) - 1]
            shown = (toks[a][1], toks[b][2])
            yield (pre[j] - pre[i], n, kw, -shown[0]), (toks[i][1], toks[j - 1][2]), shown


def find(q: str, known_bad: bool = False) -> Optional[Dict[str, Any]]:
    """None when the statement reads as OQL (or is empty, or is OQL still being typed).
    Else one of:
      {"kind": "typo", "start", "end", "word", "fix"}
      {"kind": "plain", "start", "end", "text", "rest": <OQL> | None}
    Offsets are code points into `q`. `rest` (the statement without the plain words) is for
    the case set and reviews; the editor sends the whole statement to the assistant.
    `known_bad`: the caller already failed to parse `q`.
    shortcut: one run only; two snippets in one statement come back as one longer run or the
    whole statement."""
    if not q or not q.strip() or (not known_bad and _parses(q)):
        return None
    toks = _tokens(q)
    words = [t for t in toks if t[0] not in _SEPARATORS]
    if not words:
        return None
    whole = {"kind": "plain", "start": words[0][1], "end": words[-1][2],
             "text": q[words[0][1]:words[-1][2]], "rest": None}
    if q[words[0][1]:words[0][2]].lower() != "get":
        return whole
    # still typing an OQL phrase at the end (`... since`, `..., most cit`): not plain words
    for k in range(1, min(3, len(words) - 1) + 1):
        s = words[-k][1]
        if _is_being_typed(q[s:words[-1][2]], at_end=True) and _parses(_without(q, s, len(q))):
            return None
    typo = _typo(q, toks)
    if typo:
        return typo
    # every run, best first: the statement's own words, then the words inside each group
    runs = list(_runs(q, toks, first=1))
    for kind, s, e in toks:
        if kind == "G" and " " in q[s:e]:
            runs += _runs(q, _tokens(q[s + 1:e - 1], s + 1), first=0)
    runs.sort()
    stop = time.perf_counter() + DEADLINE
    for _, (cut_s, cut_e), (start, end) in runs:
        text = q[start:end]
        if len(text.split()) == 1 and _is_being_typed(text, at_end=False):
            continue        # one stray grammar word: a parse error, not plain words
        if time.perf_counter() > stop:
            return whole
        rest = _without(q, cut_s, cut_e)
        if _parses(rest):
            return {"kind": "plain", "start": start, "end": end, "text": text, "rest": rest}
    return whole
