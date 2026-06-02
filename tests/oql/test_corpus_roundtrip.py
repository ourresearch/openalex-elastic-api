"""
OQL v2 conformance harness — the normative round-trip test (oxjob #330).

For every row in docs/oql/corpus.yaml:
  * status ok / hint   -> parse(oql) equals the authored oqo (canonicalized),
                          AND OQO -> OQL -> OQO is the identity.
  * status error       -> parse(oql) raises OQLError whose .code == diagnostic.
  * status boundary    -> documented non-representable; not executed here.

Run:  .venv-oql/bin/python -m pytest tests/oql/test_corpus_roundtrip.py -q
"""
import os

import pytest
import yaml

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "oql", "corpus.yaml")


def _load_rows():
    with open(CORPUS) as fh:
        data = yaml.safe_load(fh)
    return data["rows"]


ROWS = _load_rows()
OK_ROWS = [r for r in ROWS if r["status"] in ("ok", "hint")]
ERR_ROWS = [r for r in ROWS if r["status"] == "error"]


def _canon(oqo: OQO) -> dict:
    return canonicalize_oqo(oqo).to_dict()


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_oql_parses_to_authored_oqo(row):
    """The hand-authored OQL means exactly the authored OQO (independent oracle)."""
    if "oqo" not in row:
        pytest.skip("no explicit oqo oracle (round-trip-only row)")
    got = _canon(parse(row["oql"]))
    want = _canon(OQO.from_dict(row["oqo"]))
    assert got == want, f"{row['id']}: parse(oql) != authored oqo"


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_roundtrip_identity(row):
    """OQO -> OQL -> OQO is the identity (the normative round-trip)."""
    # Start from the authored oqo when present, else from parse(oql).
    start = OQO.from_dict(row["oqo"]) if "oqo" in row else parse(row["oql"])
    start_c = canonicalize_oqo(start)
    rendered = render(start_c)
    back = canonicalize_oqo(parse(rendered))
    assert start_c.to_dict() == back.to_dict(), (
        f"{row['id']}: OQO->OQL->OQO not identity\n  OQL: {rendered}")


@pytest.mark.parametrize("row", ERR_ROWS, ids=[r["id"] for r in ERR_ROWS])
def test_error_cases_have_named_diagnostic(row):
    """Every ✗ case raises a loud, named diagnostic (never a silent/wrong result)."""
    with pytest.raises(OQLError) as exc:
        parse(row["oql"])
    assert exc.value.code == row["diagnostic"], (
        f"{row['id']}: expected {row['diagnostic']}, got {exc.value.code}")
    assert exc.value.fixit, f"{row['id']}: diagnostic must carry a fix-it"


def test_corpus_covers_every_locked_behavior():
    """Spec self-check: each EXPLORE §2 locked behavior has >=1 corpus case."""
    ids = {r["id"] for r in ROWS}
    required = {
        # entity refs, sets, annotations
        "ENT1", "ENT3", "ENT4", "ENT5", "ENT6",
        # booleans / precedence / casing
        "BOOL1", "BOOL2", "BOOL3", "BOOL4",
        # the 9 gauntlet cases
        "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
        # proximity / wildcard / semantic / exact / stemmed-phrase
        "PW1", "PW4", "PW6", "PW7", "PW8", "PW9", "PW10", "PW11", "PW12",
    }
    missing = required - ids
    assert not missing, f"corpus missing locked-behavior cases: {sorted(missing)}"
