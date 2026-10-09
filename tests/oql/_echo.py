"""The step words of the canonical echo (oxjob #1555), for tests written in the
launch form (`; then group ...; then summarize using ...`).

`modern(text)` turns a one-line launch-form query into today's echo
(`; then, group ...; finally, summarize using ...`); `launch_form(text)` goes back.
Both split only at top-level `; ` (outside parentheses and quotes), so nested
queries keep their own steps.
"""
import re

from query_translation.oql_pipeline import SUMMARIZE, YEAR_WORDS, english_list, transitions

_OPENERS = ("then, ", "first, ", "finally, ", "next, ", "lastly, ", "then ")


def _top_level_parts(text):
    parts, depth, quoted, start = [], 0, False, 0
    for i, c in enumerate(text):
        if c == '"':
            quoted = not quoted
        elif not quoted and c == "(":
            depth += 1
        elif not quoted and c == ")":
            depth -= 1
        elif not quoted and depth == 0 and text.startswith("; ", i):
            parts.append(text[start:i])
            start = i + 2
    parts.append(text[start:])
    return parts


def _bare(step):
    for w in _OPENERS:
        if step.startswith(w):
            return step[len(w):]
    return step


def _inner(text, fn):
    """Apply fn to every parenthesized nested query (`(get ...)`)."""
    out, i = [], 0
    while i < len(text):
        if text.startswith("(get ", i):
            depth, j, quoted = 0, i, False
            while j < len(text):
                c = text[j]
                if c == '"':
                    quoted = not quoted
                elif not quoted and c == "(":
                    depth += 1
                elif not quoted and c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("(" + fn(text[i + 1:j]) + ")")
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


_ANNOTATED = re.compile(r"(?P<id>\b[A-Za-z]?\d+|\b[A-Z]{2}) \[(?P<name>[^\]]+)\]")
_SINGLE = re.compile(r'(?P<op> is| is not| >=| <=| >| <| =|\bsample|\bseed|\bbins of) '
                     r'\((?P<v>-?[^()\s"]+|"[^"]*")\)')


_FIELD_VALUE = re.compile(r"(?P<field>\b[a-zA-Z][a-zA-Z' -]*?) (?P<op>is not|is) "
                          r"(?!(?:in|not|null|unknown)\b)(?P<v>[A-Za-z0-9][\w-]*)(?=$|[\s;),])")
_SET_SUBJECTS = ("co-author", "collaborator", "that author", "that institution")


def _link(field, v):
    """An entity value as the echo writes it with no name resolver: a closed
    vocabulary's link (`[Kenya](KE)`), else `(I63966007)`; None if not an entity."""
    from query_translation import oql_lang as L
    from query_translation.oql_renderer import _builtin_name
    if field.lower().endswith(_SET_SUBJECTS):
        return f"({v})"
    words = field.lower().split()
    for k in range(len(words)):
        fld = L._ALIAS.get(" ".join(words[k:]))
        if fld is None:
            continue
        ns = (L.entity_type_for_column(fld.column)
              if fld.column not in L._SELF_ID_COLUMNS else None)
        if ns is None or fld.kind not in ("id", "enum") or v.startswith("col_"):
            return None
        name = _builtin_name(ns, v)
        return f"[{name}]({v})" if name else f"({v})"
    return None


def bare_values(text):
    """Today's value forms (oxjob #1555): an annotated ID `I1 [Name]` becomes the link
    `[Name](I1)`; an entity value is a link (`[Kenya](KE)`, `(I63966007)`); any other
    single value loses its parentheses."""
    text = _ANNOTATED.sub(lambda m: f'({m["id"]})' if m["name"] == "no entity found"
                          else f'[{m["name"]}]({m["id"]})', text)

    def entity(m):
        link = _link(m["field"], m["v"])
        return m[0] if link is None else f'{m["field"]} {m["op"]} {link}'
    text = _SINGLE.sub(lambda m: f'{m["op"]} {m["v"]}', text)
    return _FIELD_VALUE.sub(entity, text)


_SET_VERBS = [
    (" doesn't cite works in (", " doesn't cite any work in the set ("),
    (" cites works in (", " cites a work in the set ("),
    (" isn't cited by works in (", " isn't cited by any work in the set ("),
    (" cited by works in (", " cited by a work in the set ("),
    (" isn't related to works in (", " isn't related to any work in the set ("),
    (" related to works in (", " related to a work in the set ("),
    (" is not in (", " is not in the set ("),
    (" is in (", " is in the set ("),
]
_PHRASE = re.compile(r"^get (?P<base>\w+)(?P<where> where .*?)?"
                     r"(?:; (?:then|finally), get (?P<to>\w+) of those (?P=base))?$")


def _balanced(text, i):
    """The index of the `)` matching the `(` at text[i]."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return len(text) - 1


def named_sets(text):
    """`into ((A), (B))` -> `into (A, B)` (oxjob #1555)."""
    out, i = [], 0
    while True:
        k = text.find(" into ((", i)
        if k < 0:
            return "".join(out) + text[i:]
        start = k + len(" into ")
        end = _balanced(text, start)
        items, depth, cur = [], 0, ""
        for c in text[start + 1:end]:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if c == "," and depth == 0:
                items.append(cur.strip())
                cur = ""
            else:
                cur += c
        items.append(cur.strip())
        items = [x[1:-1] if x.startswith("(") and _balanced(x, 0) == len(x) - 1 else x
                 for x in items]
        out.append(text[i:start] + "(" + ", ".join(items) + ")")
        i = end + 1


def set_words(text):
    """Sets (oxjob #1555): `in the set (...)`, `it cites a work in the set (...)`; a saved
    collection reads `in the collection (col_x)` (Jason 2026-10-08)."""
    for old, new in _SET_VERBS:
        text = text.replace(old, new)
    return re.sub(r"in the set (\(col_|\[[^\]]*\]\(col_)", r"in the collection \1", text)


def set_phrase(inner):
    """A plain query in a set's parentheses as a set phrase: `works where X`,
    `authors of works where X`."""
    m = _PHRASE.match(inner)
    if m is None:
        return inner
    phrase = m["base"] + (m["where"] or "")
    return f'{m["to"]} of {phrase}' if m["to"] else phrase


def _modern_inner(text):
    return set_phrase(modern(text))


_GROUP = re.compile(r"^group those (\w+) (again )?(by|into) (.*)$")


def merge_splits(steps):
    """`group those works by A; then group those works again by B` -> `group those
    works by A and B` (Jason 2026-10-08): `and by` after a group filter or bins, the
    Oxford comma for three plain splits; a later bins split reads `by <field> bins`."""
    out, run = [], []

    def flush():
        if not run:
            return
        noun = run[0][0]
        parts = [(m3, rest) for _n, m3, rest in run]
        plain = len(parts) >= 3 and all(m3 == "by" and " where " not in r for m3, r in parts)
        text = f"group those {noun} {parts[0][0]} {parts[0][1]}"
        for i in range(1, len(parts)):
            m3, rest = parts[i]
            prev_m3, prev = parts[i - 1]
            if plain:
                text += (", and " if i == len(parts) - 1 else ", ") + rest
            elif m3 == "into":
                text += " and by " + rest
            elif " where " in prev or prev_m3 == "into":
                text += " and by " + rest
            else:
                text += " and " + rest
        out.append(text)
        run.clear()

    for s in steps:
        m = _GROUP.match(s)
        if m and m[3] != "into" or m and " bins " in m[4]:
            if m[2] and run:
                run.append((m[1], m[3], m[4]))
                continue
            flush()
            run.append((m[1], m[3], m[4]))
            continue
        flush()
        out.append(s)
    flush()
    return out


# `year` as a condition's field (not `start year`, not a split's `by year`)
_YEAR = r"(?:(?<=where )|(?<=and )|(?<=or )|(?<=\()|(?<=, )|(?<=versus )|(?<=compare )|(?<=^))year"


def year_words(text):
    """Years in words (Jason 2026-10-09): `year >= 2020` -> `published since 2020`, `year is
    2023` -> `published in 2023`, `year >= 2015 and year <= 2024` -> `published from 2015
    through 2024` (a compared range loses its parentheses)."""
    text = re.sub(_YEAR + r" >= (\d{4}) and year <= (\d{4})",
                  lambda m: (f"published from {m[1]} through {m[2]}" if m[1] <= m[2] else m[0]), text)
    text = re.sub(_YEAR + r" (>=|>|<=|<) (\d{4})", lambda m: f"published {YEAR_WORDS[m[1]]} {m[2]}", text)
    text = re.sub(_YEAR + r" is (?!not\b)(?=\(|\d)", "published in ", text)
    return re.sub(r"(compare |versus )\((published from \d{4} through \d{4})\)", r"\1\2", text)


def modern(text):
    text = year_words(named_sets(set_words(bare_values(text))))
    head, *steps = _top_level_parts(_inner(text, _modern_inner))
    steps = merge_splits([_bare(s) for s in steps])
    steps = [SUMMARIZE + english_list(re.split(r",? and |, ", s[len(SUMMARIZE):]))
             if s.startswith(SUMMARIZE) else s for s in steps]
    return "; ".join([head] + [f"{w}, {s}" for w, s in zip(transitions(len(steps)), steps)])


def launch_form(text):
    head, *steps = _top_level_parts(_inner(text, launch_form))
    steps = [_bare(s) for s in steps]
    # `calculate` was the launch word for the summary; it's gone (Jason 2026-10-08), so
    # the launch form keeps the old openers and commas with today's `summarize using`
    steps = [SUMMARIZE + ", ".join(re.split(r",? and |, ", s[len(SUMMARIZE):]))
             if s.startswith(SUMMARIZE) else s for s in steps]
    return "; ".join([head] + [f"then {s}" for s in steps])
