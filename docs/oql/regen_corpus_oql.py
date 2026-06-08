#!/usr/bin/env python3
"""Regenerate the DERIVED fields of every ok/hint corpus row, in place.

Three derived fields are pure functions of the authored `oql`/`oqo` and the
production translator, so they must never be hand-maintained:

  * `oql`    — the canonical, width-aware multi-line form (oxjob #376 Phase 2).
  * `oxurl`  — the classic openalex.org SERP URL string, rendered via
               query_translation/url_renderer.py (oxjob #384). `null` when the
               OQO is genuinely not URL-expressible (the `oql-only` rows, where
               the renderer raises — e.g. row 78's cross-match-mode OR).
  * `oqo`    — materialized for the one ok row that omits its oracle (row 78, the
               114-leaf zd#8101 SR tree), so the GUI mirror generator
               (openalex-gui/scripts/gen_oql_corpus.py) can be a pure yaml->js
               copy with no live-parser call (oxjob #384).

In-place, block-oriented rewrite: only the derived fields of ok/hint rows change;
all comments, section headers, provenance, notes, and the authored `oql`/`oqo`
of every other row are preserved verbatim. error / out-of-scope rows are left
untouched (their oql is intentionally non-canonical or invalid, and they are
non-queries with no oxurl).

The corpus is a human-facing surface (the #345 playground mirrors it into
`openalex-gui/src/oqlCorpus.js` and renders these fields verbatim), so we **keep
the curated `[display name]` annotations** in `oql` rather than emit bare IDs:
the pure test env has no Elasticsearch, so names are supplied by a resolver
harvested from the corpus's own existing annotations (`harvest_names`,
first-wins per ID). `oxurl` renders raw IDs (no resolver needed).

Run from repo root:
    python docs/oql/regen_corpus_oql.py            # rewrite in place
    python docs/oql/regen_corpus_oql.py --check     # exit 1 if anything is stale

The no-drift guards in CI (.github/workflows/oql-gate.yml -> tests/oql/) are
tests/oql/test_formatter.py::test_corpus_oql_is_canonical (oql) and
tests/oql/test_corpus_roundtrip.py::test_corpus_oxurl_is_canonical (oxurl).
"""
import argparse
import os
import re
import sys

import yaml

from tests.oql.oql_v2 import parse, render
from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_renderer import render_oqo_to_url, URLRenderError

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.yaml")

# OpenAlex entity IDs are an uppercase letter + digits (I…/A…/F…/S…/T…/…); every
# `[name]` annotation in the corpus decorates one of these. (Country/SDG/lang
# codes were authored bare, so they stay bare — readable already: `country is US`.)
_ANNOT_RE = re.compile(r"([A-Z]\d{4,})\s+\[([^\]]+)\]")

# oxurl component order — the readable order users/the GUI emit. `search.semantic`
# rides as its own top-level param (vector search has no `filter=` form, #363), so
# it leads. Mirror of query_translation.views._OXURL_COMPONENT_ORDER, but the
# corpus/GUI render an absolute openalex.org URL with the readable SAFE set below.
_OXURL_COMPONENT_ORDER = (
    "search.semantic", "filter", "sort", "group_by", "sample", "select",
    "seed", "per_page", "page", "cursor",
)
# Filter/sort syntax chars are structural -- preserve them; percent-encode the
# rest (spaces, +, ", #, &, %, ...) so the stored oxurl is a valid URL. (Byte
# identical to the historical openalex-gui generator, so unchanged rows don't
# churn.)
_OXURL_SAFE = ":|,!<>=-.~*()/"


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


def canonical_oql(oql: str, resolver) -> str:
    return render(canonicalize_oqo(parse(oql)), resolver=resolver)


def canonical_oqo_dict(row: dict) -> dict:
    """Canonical OQO for an ok/hint row: from the authored oqo when present,
    else parsed from the oql (row 78)."""
    start = OQO.from_dict(row["oqo"]) if row.get("oqo") is not None else parse(row["oql"])
    return canonicalize_oqo(start).to_dict()


def build_oxurl(oqo_dict: dict):
    """Render an OQO dict to the classic openalex.org SERP URL string, or return
    None when it is not URL-expressible (renderer raises URLRenderError -- the
    `oql-only` rows)."""
    from urllib.parse import quote
    try:
        components = render_oqo_to_url(OQO.from_dict(oqo_dict))
    except URLRenderError:
        return None
    entity = oqo_dict.get("get_rows", "works")
    parts = []
    for key in _OXURL_COMPONENT_ORDER:
        val = components.get(key)
        if val is None or val == "":
            continue
        parts.append(f"{key}=" + quote(str(val), safe=_OXURL_SAFE))
    return f"https://openalex.org/{entity}" + ("?" + "&".join(parts) if parts else "")


def emit_oql_field(canon: str) -> list:
    """Render the `oql:` field lines (2-space row indent) for a canonical form:
    a single-quoted scalar when one line, else a `|-` literal block scalar."""
    if "\n" not in canon:
        return [f"  oql: '{canon.replace(chr(39), chr(39) * 2)}'\n"]
    lines = ["  oql: |-\n"]
    lines += [f"    {ln}\n" if ln else "\n" for ln in canon.split("\n")]
    return lines


def emit_oxurl_field(oxurl) -> list:
    """One `oxurl:` line. `null` (renderer raised) -> the YAML null literal."""
    if oxurl is None:
        return ["  oxurl: null\n"]
    # The value is a URL: percent-encoded, so it has no YAML-special chars except
    # possibly `:` mid-string -> single-quote to be safe + stable.
    return [f"  oxurl: '{oxurl.replace(chr(39), chr(39) * 2)}'\n"]


def emit_oqo_field(oqo_dict: dict) -> list:
    """Materialize a (possibly huge) OQO as an indented flow-style block under
    `  oqo:`. Flow style is whitespace-insensitive, so the uniform 4-space indent
    on continuation lines parses back to the same dict (idempotent)."""
    dumped = yaml.dump(oqo_dict, default_flow_style=True, width=92,
                       sort_keys=False, allow_unicode=True).rstrip("\n")
    out_lines = dumped.split("\n")
    lines = [f"  oqo: {out_lines[0]}\n"]
    lines += [f"    {ln.lstrip()}\n" for ln in out_lines[1:]]
    return lines


# --- block-oriented rewrite -------------------------------------------------

def split_blocks(src: list):
    """Split corpus lines into (preamble, [block, ...]). A block is one row:
    from its `- id:` line up to (but excluding) the next `- id:` line, so the
    inter-row section-divider comments ride with the preceding block."""
    first = next(i for i, ln in enumerate(src) if ln.startswith("- id:"))
    preamble = src[:first]
    blocks = []
    cur = [src[first]]
    for ln in src[first + 1:]:
        if ln.startswith("- id:"):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    blocks.append(cur)
    return preamble, blocks


def rewrite_block(block: list, row: dict, resolver) -> list:
    """Return the rewritten lines for one row block."""
    status = row.get("status")
    if status not in ("ok", "hint"):
        return list(block)  # error / out-of-scope: never touched

    oqo_dict = canonical_oqo_dict(row)
    oxurl = build_oxurl(oqo_dict)

    out = []
    i, n = 0, len(block)
    have_oxurl_line = any(re.match(r"  oxurl:(\s|$)", ln) for ln in block)
    have_oqo_line = any(re.match(r"  oqo:(\s|$)", ln) for ln in block)
    while i < n:
        line = block[i]

        # --- oql: canonicalize (single scalar or |- block) ---
        if re.match(r"  oql:(\s|$)", line):
            rhs = line.split("oql:", 1)[1].strip()
            if rhs.startswith("|") or rhs.startswith(">"):
                j = i + 1
                buf = []
                while j < n and block[j].startswith("    "):
                    buf.append(block[j][4:].rstrip("\n"))
                    j += 1
                val = "\n".join(buf).strip()
                consumed = j - i
            else:
                val = yaml.safe_load(line.split("oql:", 1)[1])
                consumed = 1
            # `oql` is derived from the authored `oqo` oracle (canonical form),
            # not re-parsed from the previous `oql` — so the oracle is the single
            # source of truth and a pure surface-syntax migration (e.g. the #363
            # parens-bag spec) needs no hand-edits to the stored oql strings.
            out.extend(emit_oql_field(
                render(OQO.from_dict(oqo_dict), resolver=resolver)))
            i += consumed
            continue

        # --- oxurl: replace existing line with the freshly rendered value ---
        if re.match(r"  oxurl:(\s|$)", line):
            out.extend(emit_oxurl_field(oxurl))
            i += 1
            continue

        # --- oxurl_status: keep it, then inject oxurl right after if absent ---
        if re.match(r"  oxurl_status:(\s|$)", line):
            out.append(line)
            if not have_oxurl_line:
                out.extend(emit_oxurl_field(oxurl))
                have_oxurl_line = True
            i += 1
            continue

        out.append(line)
        i += 1

    # --- oqo: materialize for ok rows that omit it (row 78) ---
    if not have_oqo_line:
        # insert before the block's trailing blank lines (keep row separation)
        tail = 0
        while tail < len(out) and out[len(out) - 1 - tail].strip() == "":
            tail += 1
        insert_at = len(out) - tail
        out[insert_at:insert_at] = emit_oqo_field(oqo_dict)

    return out


def regenerate(src: list) -> list:
    resolver = make_resolver(harvest_names("".join(src)))
    data = yaml.safe_load("".join(src))
    rows_by_id = {r["id"]: r for r in data["rows"]}

    preamble, blocks = split_blocks(src)
    out = list(preamble)
    for block in blocks:
        m = re.match(r"- id:\s*(\d+)", block[0])
        row = rows_by_id[int(m.group(1))]
        out.extend(rewrite_block(block, row, resolver))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if corpus.yaml's derived fields are stale "
                         "(don't write); used by the CI drift gate")
    args = ap.parse_args()

    with open(CORPUS) as fh:
        src = fh.readlines()
    out = regenerate(src)

    if args.check:
        if out != src:
            sys.stderr.write(
                "corpus.yaml derived fields are STALE — run "
                "`python docs/oql/regen_corpus_oql.py` and commit.\n")
            return 1
        print("corpus.yaml derived fields are up to date.")
        return 0

    with open(CORPUS, "w") as fh:
        fh.writelines(out)
    changed = sum(1 for a, b in zip(out, src) if a != b) + abs(len(out) - len(src))
    print(f"regenerated corpus.yaml ({changed} line(s) changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
