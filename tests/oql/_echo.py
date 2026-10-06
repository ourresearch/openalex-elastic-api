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


def bare_values(text):
    """Today's value forms (oxjob #1555): `I1 [Name]` -> `Name [I1]` (a bare ID for
    `[no entity found]`), and one value loses its parentheses."""
    text = _ANNOTATED.sub(lambda m: m["id"] if m["name"] == "no entity found"
                          else f'{m["name"]} [{m["id"]}]', text)
    return _SINGLE.sub(lambda m: f'{m["op"]} {m["v"]}', text)


def modern(text):
    text = bare_values(text)
    head, *steps = _top_level_parts(_inner(text, modern))
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
