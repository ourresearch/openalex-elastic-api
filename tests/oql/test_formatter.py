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
from query_translation.oql_renderer import make_engine_resolver
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "oql", "corpus.yaml")

def _fmt(oql: str) -> str:
    """parse -> canonicalize -> canonical (width-aware) OQL (no name resolver —
    tests pure layout)."""
    return render(canonicalize_oqo(parse(oql)))


# The committed corpus keeps its curated `[display name]` annotations (it's a
# human-facing surface — the #345 playground renders `row.oql` verbatim). The
# pure test env has no Elasticsearch, so names come from a PRODUCTION-EQUIVALENT
# resolver — opaque-ID names harvested from the corpus's own annotations (+ the
# supplemental real names) wrapped by make_engine_resolver, which adds the
# config/*.yaml builtin tables for closed vocabs (country / language / field /
# subfield / domain / sdg). Mirrors docs/oql/regen_corpus_oql.py exactly (KEEP IN
# SYNC), so the corpus annotates as production renders + the no-drift check holds.
_ANNOT_RE = re.compile(r"([A-Z]\d{4,})\s+\[([^\]]+)\]")
_SUPPLEMENTAL_NAMES = {
    "A5022654839": "Terry Law",
    "W1984893742": "Uncertainty and Pension Systems Reforms",
    "A5018352470": "Kenji Takizawa",
    # Keyword entities for the zd#8101 / #434 SR rows (2026-06-12). KEEP IN SYNC
    # with docs/oql/regen_corpus_oql.py._SUPPLEMENTAL_NAMES.
    "ANIMAL-MODEL": "Animal model",
    "ELECTRONIC-CIGARETTE": "Electronic cigarette",
    "ANTICOAGULANT": "Anticoagulant",
    "CENTRAL-VENOUS-CATHETER": "Central venous catheter",
}
with open(CORPUS) as _fh:
    _NAMES: dict = dict(_SUPPLEMENTAL_NAMES)
    for _id, _name in _ANNOT_RE.findall(_fh.read()):
        _NAMES.setdefault(_id, _name)
_RESOLVER = make_engine_resolver(
    lambda key: _NAMES.get(key.rsplit("/", 1)[-1].upper())
)


def test_supplemental_names_in_sync_with_regen():
    """`_SUPPLEMENTAL_NAMES` is duplicated here and in
    docs/oql/regen_corpus_oql.py (the pure test env can't cleanly share it). If
    they drift, the corpus regenerates with names this gate renders differently
    -> a confusing per-row `test_corpus_oql_is_canonical` failure. This guard
    turns that into one loud, localized failure that names the exact diff.
    (Caught the missing keyword names that bit 2026-06-12.)"""
    import sys
    sys.path.insert(0, os.path.dirname(CORPUS))  # docs/oql/
    from regen_corpus_oql import _SUPPLEMENTAL_NAMES as _REGEN_NAMES
    only_here = set(_SUPPLEMENTAL_NAMES) - set(_REGEN_NAMES)
    only_regen = set(_REGEN_NAMES) - set(_SUPPLEMENTAL_NAMES)
    val_diffs = {k: (_SUPPLEMENTAL_NAMES[k], _REGEN_NAMES[k])
                 for k in set(_SUPPLEMENTAL_NAMES) & set(_REGEN_NAMES)
                 if _SUPPLEMENTAL_NAMES[k] != _REGEN_NAMES[k]}
    assert _SUPPLEMENTAL_NAMES == _REGEN_NAMES, (
        "_SUPPLEMENTAL_NAMES drifted between tests/oql/test_formatter.py and "
        "docs/oql/regen_corpus_oql.py — keep them identical:\n"
        f"  only in test_formatter:    {only_here}\n"
        f"  only in regen_corpus_oql:  {only_regen}\n"
        f"  value mismatches:          {val_diffs}"
    )


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
    # (a) short query stays inline (body wraps in `all (…)`, decision 32)
    "works where it's open access and type is article":
        "works where all (it's open access, type is article)",

    # (b) medium query explodes: the body is an `all (…)` keyword group, one
    # clause per line, comma after each but the last (decision 32; the entity
    # head stays on the `where` line, oxjob #363).
    "works where it's open access and publication_year >= 2020 and type is "
    "article and has_doi is true and language is en":
        "works where all (\n"
        "    it has a DOI,\n"
        "    language is en,\n"
        "    it's open access,\n"
        "    year >= 2020,\n"
        "    type is article\n"
        "  )",

    # (c) a nested boolean that fits stays inline (`any (…)`) inside the exploded
    # `all (…)` parent.
    "works where (institution is I27837315 or type is article) and "
    "publication_year >= 2020 and language is en":
        "works where all (\n"
        "    language is en,\n"
        "    year >= 2020,\n"
        "    any (institution is I27837315, type is article)\n"
        "  )",

    # (d) a search group <=8 items -> the `any (…)` keyword group, one per line,
    # comma-separated (decision 32 retired the decision-25 leading connective).
    'works where title has ("randomized controlled trial" or '
    '"systematic review" or "meta analysis" or "clinical practice guideline")':
        "works where title has any (\n"
        '    "clinical practice guideline",\n'
        '    "meta analysis",\n'
        '    "randomized controlled trial",\n'
        '    "systematic review"\n'
        "  )",

    # (e) a value group >8 items -> fill/pack to width, comma-separated
    "works where language is (en or zh or es or fr or de or ja or pt or ru or ko "
    "or it or ar or nl or pl or tr or sv or cs or fa or uk or vi or da)":
        "works where language is any (\n"
        "    ar, cs, da, de, en, es, fa, fr, it, ja, ko, nl, pl, pt, ru, sv, tr, uk, vi,\n"
        "    zh\n"
        "  )",

    # (f) directives on their own lines at col 0. Input keeps the legacy `;`
    # separators to prove the parser still accepts them (back-compat); the
    # canonical output drops them (oxjob #377). The body is an `all (…)` group.
    "works where it's open access and publication_year >= 2020 and type is "
    "article and language is en ; group by publication_year ; sort by "
    "cited_by_count desc":
        "works where all (\n"
        "    language is en,\n"
        "    it's open access,\n"
        "    year >= 2020,\n"
        "    type is article\n"
        "  )\n"
        "group by year\n"
        "sort by citation count desc",

    # (g) a nested boolean group that is too wide -> the `any (…)` group explodes
    "works where publication_year >= 2020 and (institution is I27837315 or "
    "funder is F4320332161 or source is S137773608 or author is A5023888391)":
        "works where all (\n"
        "    year >= 2020,\n"
        "    any (\n"
        "      author is A5023888391,\n"
        "      institution is I27837315,\n"
        "      funder is F4320332161,\n"
        "      source is S137773608\n"
        "    )\n"
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
        # the only allowed overflow is a single unbreakable group item, which by
        # construction carries no top-level ` or `/` and ` separator to break on.
        assert " or " not in line and " and " not in line, (
            f"{row['id']}: breakable line exceeds {HARD_CEILING} cols: {line!r}")


# ---------------------------------------------------------------------------
# Test 7 — row showcase: the long SR query is readable, fill-mode, round-trips.
# ---------------------------------------------------------------------------
def test_long_sr_query_showcase():
    row = max(OK_ROWS, key=lambda r: len(r["oql"]))   # the corpus' widest query
    out = _fmt(row["oql"])
    assert "\n" in out, "the widest corpus query must lay out multi-line"
    assert ("has any (" in out or "has all (" in out), \
        "keyword-group search groups must survive (decision 32)"
    assert _oqo(out) == _oqo(row["oql"]), "showcase must round-trip"
    assert _fmt(out) == out, "showcase must be idempotent"
    assert max(len(l) for l in out.split("\n")) <= FORMAT_WIDTH, \
        "packed lines stay within the soft target"


def test_short_query_stays_inline():
    out = _fmt("works where type is article")
    assert out == "works where type is article"
    assert "\n" not in out


# ---------------------------------------------------------------------------
# Commas don't separate items in a BARE (…) group (#363): that's a loud error.
# Commas ARE the separator inside an `any`/`all` list (decision 31) — see
# test_any_all_of.py. The connective is the idempotence anchor.
# ---------------------------------------------------------------------------
def test_commas_in_bare_group_are_rejected():
    from query_translation.oql_lang import OQLError
    for q in ("works where type is (article, review)",
              "works where title has (cat, dog)"):
        with pytest.raises(OQLError) as ei:
            _oqo(q)
        assert ei.value.code == "OQL_COMMA_IN_GROUP", q
    # the parens-bag form is what works ...
    assert _oqo("works where type is (article or review)") == \
        _oqo("works where type is (review or article)")
    # ... and so does the comma-separated `any` sugar (same OQO).
    assert _oqo("works where type is any (article, review)") == \
        _oqo("works where type is (article or review)")


# ---------------------------------------------------------------------------
# Test 9 — the committed corpus `oql` fields are the canonical multi-line form
# (no drift): re-rendering each OQO reproduces the stored string exactly.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_corpus_oql_is_canonical(row):
    assert row["oql"] == _fmt_named(row["oql"]), (
        f"{row['id']}: corpus oql is not its own canonical form — "
        f"regenerate docs/oql/corpus.yaml (docs/oql/regen_corpus_oql.py)")
