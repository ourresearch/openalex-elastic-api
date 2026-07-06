"""
OQL v2 — the conformance oracle, now a thin re-export of the production engine.

Historically this file *was* a standalone reference implementation, deliberately
separate from the production translator (oxjob #330). As of oxjob #376 the
production engine and the oracle are the SAME code: the engine was promoted
verbatim into `query_translation/oql_lang.py`, and this module re-exports it.

Keeping this import path (`tests.oql.oql_v2`) lets the normative corpus harness
(`tests/oql/test_corpus_roundtrip.py`) and `gap_report.py` keep working unchanged
while there is now exactly one engine to test.

See `query_translation/oql_lang.py` for the implementation and design anchors.
"""
import os
import sys

# Load the OQO data model + the engine WITHOUT triggering the Flask-heavy
# package __init__ (the harness runs without the app). _qt_loader registers a
# stub `query_translation` package in sys.modules before any submodule import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import tests.oql._qt_loader  # noqa: F401  (registers the stub package)

from query_translation.oql_lang import *  # noqa: F401,F403,E402  (re-export the engine)
from query_translation.oql_lang import (  # noqa: E402  (explicit names for tooling)
    OQLError,
    OQLHint,
    parse,
    render,
    lex,
)
