"""OQL core v3 (oxjob #1555): the 44 review cases render and parse back exactly.

Each case in core_v3_cases.json carries the canonical v3 text Jason approved over three
review drafts (2026-10-11) and the OQO it means. Run:
    PYTHONPATH=. pytest tests/oql/test_core_v3.py -q --noconftest
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.oqo import OQO  # noqa: E402
from query_translation.oql_core import render_core  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "core_v3_cases.json")))
NAMES = DATA["names"]
CASES = DATA["cases"]


def resolver(value, column=None):
    return NAMES.get(str(value))


def _id(c):
    return f"{c['case'] or c['label']}-{c['shape']}"


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_renders(c):
    assert render_core(OQO.from_dict(c["oqo"]), resolver) == c["new"]
