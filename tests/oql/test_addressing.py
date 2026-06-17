"""
OQL decimal-addressing conformance (oxjob #474).

Asserts the address scheme in docs/oql-addressing.md against the live engine:
  * every corpus row carrying `addr:` reproduces exactly (the normative anchor);
  * the spec's §8 worked cases number correctly (authored here, independently);
  * addressing is a pure function of the tree (whitespace-blind, deterministic);
  * `stamp_addresses` decorates the structural nodes + returns the flat map.

Run:  .venv-oql/bin/python -m pytest tests/oql/test_addressing.py -q --noconftest
"""
import os

import pytest
import yaml

# Register the stub `query_translation` package (no Flask) before importing the
# render tree, exactly like the rest of the harness.
from tests.oql.oql_v2 import parse  # noqa: F401  (also triggers _qt_loader)
from query_translation.oql_render_v2 import (
    build_tree, address_index, stamp_addresses, dotted,
)

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "oql", "corpus.yaml")


def _index_lines(oql: str):
    """The address index rendered as the corpus `addr` block's `dotted label` lines."""
    idx = address_index(build_tree(parse(oql)))
    return [f"{dotted(e['addr'])} {e['label']}" for e in idx]


# --------------------------------------------------------------------------- #
# 1. The normative anchor: every corpus row with `addr:` reproduces exactly.
# --------------------------------------------------------------------------- #

with open(CORPUS) as _fh:
    _ADDR_ROWS = [r for r in yaml.safe_load(_fh)["rows"] if r.get("addr")]


def test_corpus_has_required_addr_shapes():
    """ACCEPTANCE Test 1: ≥3 addr cases, incl. deep-merged + ≥10 + boolean."""
    assert len(_ADDR_ROWS) >= 3
    joined = "\n".join(r["addr"] for r in _ADDR_ROWS)
    assert any(len(e["addr"]) >= 3                      # a deeply nested case
               for r in _ADDR_ROWS
               for e in address_index(build_tree(parse(r["oql"]))))
    assert any(seg >= 10                                # a ≥10-item group
               for r in _ADDR_ROWS
               for e in address_index(build_tree(parse(r["oql"])))
               for seg in e["addr"])
    assert "it has an ORCID" in joined or "open access" in joined  # a boolean


@pytest.mark.parametrize("row", _ADDR_ROWS, ids=[r["id"] for r in _ADDR_ROWS])
def test_corpus_addr_reproduces(row):
    want = [ln.strip() for ln in row["addr"].strip().splitlines()]
    got = _index_lines(row["oql"])
    assert got == want, f"row {row['id']}: address index drift"


# --------------------------------------------------------------------------- #
# 2. The spec §8 worked cases, authored independently of the engine.
# --------------------------------------------------------------------------- #

WORKED_EXAMPLE = (
    "works where title has animal and it's open access "
    "and (institution is (I33213144 or I97018004) or type is article) "
    "and full text has ((dog or cat) and (play or jump))"
)
WORKED_EXPECTED = [
    "0 and",
    "1 title has", "1.0 title", "1.1 animal",
    "2 it's open access",                       # boolean: atomic, no .0/.1
    "3 ( … )", "3.0 or",
    "3.1 institution is", "3.1.0 institution", "3.1.1 I33213144", "3.1.2 I97018004",
    "3.2 type is", "3.2.0 type", "3.2.1 article",
    "4 full text has", "4.0 full text",
    "4.1 ( … )", "4.1.0 or", "4.1.1 dog", "4.1.2 cat",
    "4.2 ( … )", "4.2.0 or", "4.2.1 play", "4.2.2 jump",
]


def test_worked_example():
    assert _index_lines(WORKED_EXAMPLE) == WORKED_EXPECTED


def test_boolean_is_atomic():
    # Both polarities; each flag is a single fused node with no .0/.1.
    assert _index_lines("works where it's open access and it doesn't have a DOI") == [
        "0 and", "1 it's open access", "2 it doesn't have a DOI",
    ]
    # A single flag has no root conjunction (no `0`).
    assert _index_lines("works where it's open access") == ["1 it's open access"]


def test_merged_not_distributed():
    # One top-level clause with a nested value tree — NOT four sibling rows.
    lines = _index_lines("works where title has ((vape or vaping) and (health or harm))")
    assert lines[0] == "1 title has"          # single clause, so no `0`
    assert "1.1 ( … )" in lines and "1.1.1 vape" in lines and "1.2.2 harm" in lines
    assert not any(ln.startswith("2 ") for ln in lines)


def test_past_ten_is_dotted():
    lines = _index_lines(
        "works where title has (A or B or C or D or E or F or G or H or I or J or K or L)")
    assert "1.9 I" in lines and "1.10 J" in lines and "1.11 K" in lines and "1.12 L" in lines


def test_range_and_null():
    assert _index_lines("works where year >= 2019 and year <= 2023") == [
        "0 and", "1 year >=", "1.0 year", "1.1 2019",
        "2 year <=", "2.0 year", "2.1 2023",
    ]
    assert _index_lines("works where doi is unknown") == [
        "1 DOI is", "1.0 DOI", "1.1 unknown",
    ]


# --------------------------------------------------------------------------- #
# 3. Purity / determinism, and the stamp + flat-map convenience.
# --------------------------------------------------------------------------- #

def test_deterministic_whitespace_blind():
    a = _index_lines("works where title has animal and year >= 2019")
    b = _index_lines("works   where\n  title has animal\n  and year >= 2019\n")
    assert a == b


def test_entity_is_unaddressed():
    # `works` is the subject, not a filter node — it never appears in the index.
    idx = address_index(build_tree(parse(WORKED_EXAMPLE)))
    assert all(e["kind"] != "entity" for e in idx)


def test_stamp_addresses_decorates_nodes_and_maps():
    tree = build_tree(parse(WORKED_EXAMPLE))
    index = stamp_addresses(tree)
    # The first top-level clause is addressed [1] and stamped in place.
    assert tree["where"]["children"][0]["addr"] == [1]
    assert index[(1,)] is tree["where"]["children"][0]
    # A nested value atom resolves through the map.
    assert index[(4, 1, 2)]["display"] == "cat"
    # Token-only positions (root join, field heads) are NOT in the node map.
    assert (0,) not in index and (1, 0) not in index
