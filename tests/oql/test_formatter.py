"""
OQL canonical formatter — width-aware multi-line layout (oxjob #376 Phase 2).

The formatter (`oql_lang.format_oql`, reached via `render()`/`render_tree()`) lays
a long canonical query out multi-line by a recursive fits-or-explode pass over
the render tree; a query whose one-line form fits the 80-col target renders flat
and unchanged. The layout is a pure function of (tree, width), so it is
idempotent, and the whitespace-blind / trailing-comma-tolerant parser round-trips
every multi-line form back to the identical OQO.

Spec: docs/oql-spec.md "Canonical formatting".

Run:  .venv-oql/bin/python -m pytest tests/oql/test_formatter.py -q --noconftest
"""
import os
import re

import pytest
import yaml

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oql_lang import format_oql, FORMAT_WIDTH
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "oql", "corpus.yaml")

def _fmt(oql: str) -> str:
    """parse -> canonicalize -> canonical (width-aware) OQL (no name resolver —
    tests pure layout)."""
    return render(canonicalize_oqo(parse(oql)))


# The committed corpus keeps its curated `[display name]` annotations (it's a
# human-facing surface — the #345 playground renders `row.oql` verbatim). The
# pure test env has no Elasticsearch, so names are supplied by a resolver
# harvested from the corpus's own annotations — the same map
# docs/oql/regen_corpus_oql.py uses, so the no-drift check is stable. (Country /
# SDG / language codes were authored bare — already readable, e.g. `country is US`.)
_ANNOT_RE = re.compile(r"([A-Z]\d{4,})\s+\[([^\]]+)\]")
with open(CORPUS) as _fh:
    _NAMES: dict = {}
    for _id, _name in _ANNOT_RE.findall(_fh.read()):
        _NAMES.setdefault(_id, _name)
_RESOLVER = lambda value, column_id=None: _NAMES.get(value)


def _fmt_named(oql: str) -> str:
    """Canonical OQL with the corpus's harvested display-name resolver, so the
    `[name]` annotations are reproduced (used for the no-drift corpus check)."""
    return render(canonicalize_oqo(parse(oql)), resolver=_RESOLVER)


def _oqo(oql: str) -> dict:
    return canonicalize_oqo(parse(oql)).to_dict()


with open(CORPUS) as _fh:
    ROWS = yaml.safe_load(_fh)["rows"]
OK_ROWS = [r for r in ROWS if r["status"] in ("ok", "hint")]


# ---------------------------------------------------------------------------
# Test 6 — golden fixtures: the documented shapes render to the exact form.
# ---------------------------------------------------------------------------
GOLDENS = {
    # (a) short query stays inline
    "works where it's open access and type is article":
        "works where it's open access and type is article",

    # (b) medium query explodes into a leading-`and` chain
    "works where it's open access and publication_year >= 2020 and type is "
    "article and has_doi is true and language is en":
        "works\n"
        "where it has a DOI\n"
        "  and language is en\n"
        "  and it's open access\n"
        "  and year >= 2020\n"
        "  and type is article",

    # (c) a nested boolean that fits stays inline inside the exploded parent
    "works where (institution is I27837315 or type is article) and "
    "publication_year >= 2020 and language is en":
        "works\n"
        "where language is en\n"
        "  and year >= 2020\n"
        "  and (institution is I27837315 or type is article)",

    # (d) a value list <=8 items -> one per line, trailing comma
    'works where title contains any of ("randomized controlled trial", '
    '"systematic review", "meta analysis", "clinical practice guideline")':
        "works\n"
        "where title contains any of (\n"
        '    "clinical practice guideline",\n'
        '    "meta analysis",\n'
        '    "randomized controlled trial",\n'
        '    "systematic review",\n'
        "  )",

    # (e) a value list >8 items -> fill/pack to width, trailing comma
    "works where language is any of (en, zh, es, fr, de, ja, pt, ru, ko, it, "
    "ar, nl, pl, tr, sv, cs, fa, uk, vi, da)":
        "works\n"
        "where language is any of (\n"
        "    ar, cs, da, de, en, es, fa, fr, it, ja, ko, nl, pl, pt, ru, sv, tr, uk, vi,\n"
        "    zh,\n"
        "  )",

    # (f) directives on their own lines at col 0
    "works where it's open access and publication_year >= 2020 and type is "
    "article and language is en ; group by publication_year ; sort by "
    "cited_by_count desc":
        "works\n"
        "where language is en and it's open access and year >= 2020 and type is article\n"
        "; group by year\n"
        "; sort by citations desc",

    # (g) a nested boolean group that is too wide -> the group explodes
    "works where publication_year >= 2020 and (institution is I27837315 or "
    "funder is F4320332161 or source is S137773608 or author is A5023888391)":
        "works\n"
        "where year >= 2020\n"
        "  and (\n"
        "    author is A5023888391\n"
        "    or institution is I27837315\n"
        "    or funder is F4320332161\n"
        "    or source is S137773608\n"
        "  )",
}


@pytest.mark.parametrize("src,want", list(GOLDENS.items()),
                         ids=[f"golden-{i}" for i in range(len(GOLDENS))])
def test_golden_fixtures(src, want):
    got = _fmt(src)
    assert got == want, f"\n--- got ---\n{got}\n--- want ---\n{want}"
    # every golden must round-trip and be idempotent
    assert _oqo(got) == _oqo(src)
    assert _fmt(got) == got


# ---------------------------------------------------------------------------
# Test 2 — idempotence: re-formatting a formatted query is a no-op.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_idempotence(row):
    once = _fmt(row["oql"])
    twice = _fmt(once)
    assert twice == once, f"{row['id']}: format(format(x)) != format(x)"


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_multiline_roundtrips(row):
    """The (possibly multi-line) canonical form parses back to the same OQO."""
    out = _fmt(row["oql"])
    assert _oqo(out) == _oqo(row["oql"]), f"{row['id']}: multi-line did not round-trip"


# ---------------------------------------------------------------------------
# Test 5 — width discipline: no line over the hard ceiling except a line that
# is a single unbreakable atom (one quoted phrase / id / bare term — i.e. a
# line carrying no `, ` separator we could have broken on).
# ---------------------------------------------------------------------------
HARD_CEILING = 100


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_width_ceiling(row):
    for line in _fmt(row["oql"]).split("\n"):
        if len(line) <= HARD_CEILING:
            continue
        # the only allowed overflow is a single unbreakable list item, which by
        # construction carries no top-level `", "` separator to break on.
        assert ", " not in line, (
            f"{row['id']}: breakable line exceeds {HARD_CEILING} cols: {line!r}")


# ---------------------------------------------------------------------------
# Test 7 — row showcase: the long SR query is readable, fill-mode, round-trips.
# ---------------------------------------------------------------------------
def test_long_sr_query_showcase():
    row = max(OK_ROWS, key=lambda r: len(r["oql"]))   # the corpus' widest query
    out = _fmt(row["oql"])
    assert "\n" in out, "the widest corpus query must lay out multi-line"
    assert "contains any of (" in out, "fill-mode value lists must survive"
    assert _oqo(out) == _oqo(row["oql"]), "showcase must round-trip"
    assert _fmt(out) == out, "showcase must be idempotent"
    assert max(len(l) for l in out.split("\n")) <= FORMAT_WIDTH, \
        "packed lines stay within the soft target"


def test_short_query_stays_inline():
    out = _fmt("works where type is article")
    assert out == "works where type is article"
    assert "\n" not in out


# ---------------------------------------------------------------------------
# Parser trailing-comma tolerance (the formatter emits one in every exploded
# list; the parser must accept it so the round-trip closes).
# ---------------------------------------------------------------------------
def test_trailing_comma_tolerated():
    # equality list
    assert _oqo("works where type is any of (article, review,)") == \
        _oqo("works where type is any of (article, review)")
    # search list
    assert _oqo("works where title contains any of (cat, dog,)") == \
        _oqo("works where title contains any of (cat, dog)")
    # single item + trailing comma
    assert _oqo("works where type is any of (article,)") == \
        _oqo("works where type is article")


# ---------------------------------------------------------------------------
# Test 9 — the committed corpus `oql` fields are the canonical multi-line form
# (no drift): re-rendering each OQO reproduces the stored string exactly.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_corpus_oql_is_canonical(row):
    assert row["oql"] == _fmt_named(row["oql"]), (
        f"{row['id']}: corpus oql is not its own canonical form — "
        f"regenerate docs/oql/corpus.yaml (docs/oql/regen_corpus_oql.py)")
