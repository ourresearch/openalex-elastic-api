#!/usr/bin/env python3
"""Regenerate the `oql:` field of every ok/hint corpus row to the canonical,
width-aware multi-line form (oxjob #376 Phase 2).

In-place, line-oriented rewrite: only `oql:` scalars of ok/hint rows change;
all comments, section headers, and every other field are preserved verbatim.
error / out-of-scope rows are left untouched (their oql is intentionally
non-canonical or invalid). The no-drift guard is
tests/oql/test_formatter.py::test_corpus_oql_is_canonical.

The corpus is a human-facing surface (the #345 playground mirrors it into
`openalex-gui/src/oqlCorpus.js` and renders `row.oql` verbatim), so we **keep
the curated `[display name]` annotations** rather than emit bare IDs: the pure
test env has no Elasticsearch, so names are supplied by a resolver harvested
from the corpus's own existing annotations (`harvest_names`, first-wins per ID).
`test_corpus_oql_is_canonical` rebuilds the identical map, so the form is stable.

Run from repo root:  .venv-oql/bin/python docs/oql/regen_corpus_oql.py
"""
import os
import re
import sys

from tests.oql.oql_v2 import parse, render
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.yaml")

# OpenAlex entity IDs are an uppercase letter + digits (I…/A…/F…/S…/T…/…); every
# `[name]` annotation in the corpus decorates one of these. (Country/SDG/lang
# codes were authored bare, so they stay bare — readable already: `country is US`.)
_ANNOT_RE = re.compile(r"([A-Z]\d{4,})\s+\[([^\]]+)\]")


def harvest_names(text: str) -> dict:
    """Build a {entity_id: display_name} map from the corpus's own annotations,
    first occurrence wins (a couple of IDs carry differing loose labels across
    rows; first-wins canonicalizes each ID to one name)."""
    names: dict = {}
    for ent_id, name in _ANNOT_RE.findall(text):
        names.setdefault(ent_id, name)
    return names


def make_resolver(names: dict):
    return lambda value, column_id=None: names.get(value)


def canonical(oql: str, resolver) -> str:
    return render(canonicalize_oqo(parse(oql)), resolver=resolver)


def emit_oql_field(canon: str) -> list:
    """Render the `oql:` field lines (2-space row indent) for a canonical form:
    a single-quoted scalar when one line, else a `|-` literal block scalar."""
    if "\n" not in canon:
        return [f"  oql: '{canon.replace(chr(39), chr(39) * 2)}'\n"]
    lines = ["  oql: |-\n"]
    lines += [f"    {ln}\n" if ln else "\n" for ln in canon.split("\n")]
    return lines


def main() -> int:
    with open(CORPUS) as fh:
        src = fh.readlines()

    resolver = make_resolver(harvest_names("".join(src)))

    out = []
    status = None
    i = 0
    n = len(src)
    changed = 0
    while i < n:
        line = src[i]
        if line.startswith("- id:"):
            status = None
        m_status = re.match(r"\s+status:\s*(\S+)", line)
        if m_status:
            status = m_status.group(1).strip().strip('"').strip("'")
        m_oql = re.match(r"  oql:\s", line)
        if m_oql and status in ("ok", "hint"):
            # current oql is a single-line scalar; extract its value via yaml.
            import yaml
            val = yaml.safe_load(line.split("oql:", 1)[1])
            canon = canonical(val, resolver)
            new_lines = emit_oql_field(canon)
            if new_lines != [line]:
                changed += 1
            out.extend(new_lines)
            i += 1
            continue
        out.append(line)
        i += 1

    with open(CORPUS, "w") as fh:
        fh.writelines(out)
    print(f"regenerated {changed} oql fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
