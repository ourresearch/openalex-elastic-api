#!/usr/bin/env python3
"""Ad-hoc OQL triage helper (oxjob #363 discovery loop).

Usage: python scripts/oql_triage.py 'works where title contains foo'
       echo 'works where ...' | python scripts/oql_triage.py -

For each OQL string: parse -> OQO -> canonicalize -> round-trip OQO->OQL->OQO
identity -> render to classic OXURL. Prints a one-line classification:
  OK has-oxurl   parses, round-trips, renders a URL
  OK oql-only    parses + round-trips but renderer refuses (expressiveness win)
  ERROR <code>   parser raised an OQLError (diagnostic code)
  CRASH          unexpected exception (a real translator bug to inspect)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.oql._qt_loader  # noqa: F401  (stub package, no Flask)

from query_translation.oql_lang import parse, render, OQLError
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_renderer import render_oqo_to_url, URLRenderError  # noqa: F401

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "oql"))
from regen_corpus_oql import build_oxurl  # noqa: E402


def triage(oql: str) -> str:
    oql = oql.strip()
    if not oql:
        return ""
    try:
        oqo = parse(oql)
    except OQLError as e:
        return f"ERROR {getattr(e, 'code', '?')}  | {oql}\n        {e}"
    except Exception as e:  # noqa: BLE001
        return f"CRASH parse {type(e).__name__}: {e}  | {oql}"
    try:
        c = canonicalize_oqo(oqo)
        back = canonicalize_oqo(parse(render(c)))
        rt = "rt-ok" if c.to_dict() == back.to_dict() else "RT-DIFF"
    except Exception as e:  # noqa: BLE001
        rt = f"RT-CRASH {type(e).__name__}: {e}"
    try:
        u = build_oxurl(canonicalize_oqo(oqo).to_dict())
        if u is None:
            return f"OK oql-only {rt}  | {oql}\n        (renderer refuses URL — expressiveness win)"
        return f"OK has-oxurl {rt}  | {oql}\n        -> {u}"
    except Exception as e:  # noqa: BLE001
        return f"OK CRASH-render {rt} {type(e).__name__}: {e}  | {oql}"


def main():
    args = sys.argv[1:]
    if args == ["-"] or not args:
        lines = sys.stdin.read().splitlines()
    else:
        lines = args
    for line in lines:
        if line.strip():
            print(triage(line))


if __name__ == "__main__":
    main()
