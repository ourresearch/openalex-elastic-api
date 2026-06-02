# OQL v2 conformance harness (oxjob #330)

The runnable half of the OQL v2 spec. The prose spec is
[`docs/oql-spec.md`](../../docs/oql-spec.md); the normative cases are
[`docs/oql/corpus.yaml`](../../docs/oql/corpus.yaml).

| File | Role |
|---|---|
| `oql_v2.py` | **Reference implementation** — parser (OQL→OQO) + renderer (OQO→OQL) + diagnostics. The *executable spec*. NOT the production translator (that's `query_translation/oql_*.py`, still v1.1). |
| `test_corpus_roundtrip.py` | Asserts, for every corpus row: `parse(oql)` == the authored OQO, and **`OQO→OQL→OQO` is the identity**; every `✗` row raises its named diagnostic. |
| `gap_report.py` | Runs the **current v1.1** translator against the corpus → `docs/oql/gap_report.md` (the work-list for roadmap step 3). |
| `_qt_loader.py` | Imports `query_translation.*` submodules without the Flask-heavy package `__init__`. |

## Run

A throwaway venv avoids the full-app test deps. `--noconftest` skips the repo's
root `tests/conftest.py` (which imports the whole Flask app).

```bash
cd ~/Documents/openalex-elastic-api
python3 -m venv .venv-oql && .venv-oql/bin/pip install -q pyyaml requests pytest

# round-trip identity over the normative corpus (the green gate):
.venv-oql/bin/python -m pytest tests/oql/test_corpus_roundtrip.py -q --noconftest

# gap report against the current v1.1 impl (artifact, not a gate):
.venv-oql/bin/python tests/oql/gap_report.py
```
