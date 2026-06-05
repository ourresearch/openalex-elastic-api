#!/usr/bin/env python3
"""Renumber the OQL/OQO corpus IDs to sequential integers (oxjob #360).

Reads docs/oql/corpus.yaml top-to-bottom, assigns 1..N in file order, then:
  1. writes work/id_map.yaml  (old_semantic_id -> new_int, the permanent record)
  2. rewrites corpus.yaml `- id:` fields to the new bare ints (order preserved)
  3. rewrites nl_eval.yaml `- ref:` fields to the new ints (mnemonic comments kept)

Decisions (PLAN Q1/Q2): bare int scalar; #360 lands before #358.
Idempotency: re-running after the rewrite is a no-op for corpus (ids already int)
but would fail the ref remap (old refs gone) — run once on the semantic-ID state.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "docs/oql/corpus.yaml"
NL_EVAL = ROOT / "docs/oql/nl_eval.yaml"
ID_MAP = ROOT / "work/id_map.yaml"

ID_LINE = re.compile(r"^- id: (\S+)\s*$")


def build_map(corpus_lines):
    """old semantic id -> new int, in file order."""
    mapping = {}
    n = 0
    for line in corpus_lines:
        m = ID_LINE.match(line)
        if m:
            n += 1
            old = m.group(1)
            if old in mapping:
                sys.exit(f"duplicate id in corpus: {old}")
            mapping[old] = n
    return mapping


def rewrite_corpus(lines, mapping):
    out = []
    for line in lines:
        m = ID_LINE.match(line)
        if m:
            out.append(f"- id: {mapping[m.group(1)]}\n")
        else:
            out.append(line)
    return out


def rewrite_nl_eval(text, mapping):
    """Replace `ref: <old>` with `ref: <int>`, preserving trailing comment/space."""
    unmapped = []

    def repl(m):
        old = m.group("id")
        if old not in mapping:
            unmapped.append(old)
            return m.group(0)
        return f"{m.group('pre')}{mapping[old]}"

    # `ref:` plus spaces, then the id token (letters+digits, no `#`/space)
    new = re.sub(r"(?P<pre>ref:\s+)(?P<id>[A-Za-z][A-Za-z0-9]*)", repl, text)
    if unmapped:
        sys.exit(f"nl_eval refs not in corpus map: {sorted(set(unmapped))}")
    return new


def main():
    corpus_lines = CORPUS.read_text().splitlines(keepends=True)
    mapping = build_map(corpus_lines)
    print(f"mapped {len(mapping)} corpus ids (1..{len(mapping)})")

    # 1. id_map.yaml — permanent traceability record
    ID_MAP.parent.mkdir(exist_ok=True)
    lines = [
        "# oxjob #360: OQL/OQO corpus semantic-id -> sequential-int mapping.\n",
        "# Permanent traceability record for historical references (charter, EXPLORE,\n",
        "# Zendesk threads, #358) that still cite the old semantic ids.\n",
        "# Generated from docs/oql/corpus.yaml file order by work/renumber_corpus_ids.py.\n",
        "\n",
    ]
    lines += [f"{old}: {new}\n" for old, new in mapping.items()]
    ID_MAP.write_text("".join(lines))
    print(f"wrote {ID_MAP.relative_to(ROOT)}")

    # 2. corpus.yaml
    CORPUS.write_text("".join(rewrite_corpus(corpus_lines, mapping)))
    print(f"rewrote {CORPUS.relative_to(ROOT)}")

    # 3. nl_eval.yaml
    NL_EVAL.write_text(rewrite_nl_eval(NL_EVAL.read_text(), mapping))
    print(f"rewrote {NL_EVAL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
