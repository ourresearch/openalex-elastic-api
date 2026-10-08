"""The step words of the canonical echo (oxjob #1555), for tests written in the
launch form (`; then group ...; then calculate ...`).

`modern(text)` turns a one-line launch-form query into today's echo
(`; then, group ...; finally, summarize using ...`); `launch_form(text)` goes back.
Both split only at top-level `; ` (outside parentheses and quotes), so nested
queries keep their own steps.
"""
import re

from query_translation.oql_pipeline import SUMMARIZE, english_list, transitions

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


def set_words(text):
    """Sets (oxjob #1555): `in the set (...)`, `it cites a work in the set (...)`."""
    for old, new in _SET_VERBS:
        text = text.replace(old, new)
    return text


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


def modern(text):
    text = set_words(bare_values(text))
    head, *steps = _top_level_parts(_inner(text, _modern_inner))
    steps = [_bare(s) for s in steps]
    steps = [SUMMARIZE + english_list(s[len("calculate "):].split(", "))
             if s.startswith("calculate ") else s for s in steps]
    return "; ".join([head] + [f"{w}, {s}" for w, s in zip(transitions(len(steps)), steps)])


def launch_form(text):
    head, *steps = _top_level_parts(_inner(text, launch_form))
    steps = [_bare(s) for s in steps]
    steps = ["calculate " + ", ".join(re.split(r",? and |, ", s[len(SUMMARIZE):]))
             if s.startswith(SUMMARIZE) else s for s in steps]
    return "; ".join([head] + [f"then {s}" for s in steps])
