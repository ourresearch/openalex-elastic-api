"""Guards for the shared OQL/OQO diagnostics registry (oxjob #363).

The registry (`query_translation/diagnostics.py`) is the single source of truth for
every diagnostic code the OQL stack emits. These tests keep it honest against the two
modules that actually raise/emit codes — the parser (`oql_lang.py`, `OQL_*`) and the
OQO validator (`validator.py`, `invalid_*`) — so a new code can never ship without a
registry entry (and its fix-it).

Pure: no app boot. Run with `PYTHONPATH=. pytest tests/oql/test_diagnostics.py
--noconftest`.
"""
import os
import re

import pytest

from query_translation import diagnostics as D
from query_translation.diagnostics import (
    DIAGNOSTICS, OQLError, oql_error, parse_diagnostic, validation_diagnostic,
    default_fixit, ERROR, WARNING, PARSE, VALIDATE,
)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_QT = os.path.join(_REPO, "query_translation")


def _read(name):
    with open(os.path.join(_QT, name), encoding="utf-8") as fh:
        return fh.read()


# --- the raise sites and the registry agree ----------------------------------
def test_every_parser_code_is_registered():
    """Every `oql_error("OQL_...")` raised by the engine must be in the registry."""
    src = _read("oql_lang.py")
    raised = set(re.findall(r'oql_error\(\s*"(OQL_[A-Z_]+)"', src))
    assert raised, "expected to find OQL_* raise sites in oql_lang.py"
    missing = sorted(c for c in raised if c not in DIAGNOSTICS)
    assert not missing, f"OQL_* codes raised but not registered: {missing}"


def test_every_validator_type_is_registered():
    """Every ValidationError `type="..."` must be in the registry."""
    src = _read("validator.py")
    types = set(re.findall(r'type="([a-z_]+)"', src))
    assert types, "expected to find validator type= literals"
    missing = sorted(t for t in types if t not in DIAGNOSTICS)
    assert not missing, f"validator types emitted but not registered: {missing}"


def test_no_orphan_parse_codes():
    """Registered PARSE codes should actually be raised (catches dead/renamed codes).
    OQL_PARSE_ERROR is the editor-only generic catch-all — exempt."""
    src = _read("oql_lang.py")
    raised = set(re.findall(r'oql_error\(\s*"(OQL_[A-Z_]+)"', src))
    exempt = {"OQL_PARSE_ERROR"}
    registered_parse = {c for c, s in DIAGNOSTICS.items() if s.layer == PARSE}
    orphans = sorted(registered_parse - raised - exempt)
    assert not orphans, f"registered PARSE codes never raised: {orphans}"


# --- every diagnostic carries an actionable fix-it ---------------------------
def test_every_spec_has_a_fixit_and_summary():
    for code, spec in DIAGNOSTICS.items():
        assert spec.summary, f"{code}: missing summary"
        assert spec.default_fixit, f"{code}: missing default_fixit"
        assert spec.severity in (ERROR, WARNING), f"{code}: bad severity {spec.severity}"
        assert spec.layer in (PARSE, VALIDATE), f"{code}: bad layer {spec.layer}"


# --- the factory behaves -----------------------------------------------------
def test_oql_error_fills_default_fixit_when_omitted():
    e = oql_error("OQL_MISSING_VALUE")  # site that historically passed fixit=""
    assert isinstance(e, OQLError)
    assert e.code == "OQL_MISSING_VALUE"
    assert e.fixit == default_fixit("OQL_MISSING_VALUE")
    assert e.fixit  # non-empty


def test_oql_error_keeps_explicit_prose():
    e = oql_error("OQL_UNKNOWN_FIELD", 'unknown field "foo"', "do the thing", 7)
    assert e.message == 'unknown field "foo"'
    assert e.fixit == "do the thing"
    assert e.position == 7


def test_oql_error_rejects_unregistered_code():
    with pytest.raises(AssertionError):
        oql_error("OQL_NOT_A_REAL_CODE")


# --- the unified editor diagnostic shape -------------------------------------
def test_parse_diagnostic_shape():
    e = oql_error("OQL_LEADING_WILDCARD", "leading wildcard", "anchor it", 12)
    d = parse_diagnostic(e).to_dict()
    assert set(d) == {"code", "message", "fixit", "severity",
                      "start", "end", "location"}
    assert d["code"] == "OQL_LEADING_WILDCARD"
    assert d["start"] == d["end"] == 12
    assert d["location"] is None
    assert d["severity"] == ERROR


def test_validation_diagnostic_gains_fixit():
    """A validator error (no fix-it of its own) gets the registry fix-it + severity."""
    d = validation_diagnostic("invalid_column",
                              "x is not a property", "filter_rows[0].column_id").to_dict()
    assert d["code"] == "invalid_column"
    assert d["fixit"] == default_fixit("invalid_column")
    assert d["fixit"]  # non-empty — the bridge's whole point
    assert d["location"] == "filter_rows[0].column_id"
    assert d["start"] is None and d["end"] is None
    assert d["severity"] == ERROR


def test_validation_warning_severity():
    d = validation_diagnostic("seed_without_sample", "seed is inert", None).to_dict()
    assert d["severity"] == WARNING
