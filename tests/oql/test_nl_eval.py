"""
NL→OQO eval-set lint — the repo-side conformance gate for docs/oql/nl_eval.yaml.

Ported from the oxjob #344 harness (`oxjobs/working/nl-to-oqo-pipeline/work/
validate_nl_eval.py`) into the repo so a push-to-master gate can run it (oxjob
#363 — the standing OQL-correctness home owns the CI gate). The job-dir copy
reached into this repo via a chdir/sys.path hack and was therefore unreachable
from CI; this module is the canonical, CI-runnable version.

`nl_eval.yaml` is a SIDECAR to docs/oql/corpus.yaml: each case is either
  * {ref: <corpus-id>, nl: [...]}    inherits the gold OQO from the corpus, or
  * {id, oqo, nl: [...]}             a standalone NL-only gold (Zendesk / guides).

corpus.yaml is the SOLE source of gold-OQO truth; nl_eval inherits by `ref`. The
grader (work/grade.py) decides pass/fail on the OQO (canonical-AST match →
execution equivalence) — OQL is display-only — so these checks key on the OQO too.

Checks (hard failures = "the data is broken"):
  * structure: every case is {ref,nl} or {id,oqo,nl}; nl non-empty; each
    formulation is {text, difficulty} with difficulty in {1,2,3}.
  * refs resolve to a corpus id that carries a gold OQO.
  * every gold OQO (inherited or inline) parses, VALIDATES, and canonicalizes.
  * standalone ids are unique and don't collide with corpus ids.
  * NO standalone inline gold canonicalizes to an existing corpus row's gold —
    that should be a `ref`, else the inline copy silently diverges when the
    corpus row changes.

Coverage gates (separate test — "not enough phrasings yet", not "broken"):
  * >=60% of all corpus rows have a ref with >=3 formulations.
  * >=10 standalone NL-only cases, each citing a provenance source.

Run:  ./venv/bin/python -m pytest tests/oql/test_nl_eval.py -q
(needs the prod deps — validate_oqo pulls the property catalog — same as CI.)
"""
import json
import os

import pytest
import yaml

# Load the OQO data model + validator WITHOUT triggering the Flask-heavy package
# __init__ (mirrors tests/oql/oql_v2.py). _qt_loader registers a stub
# `query_translation` package in sys.modules before any submodule import.
import tests.oql._qt_loader  # noqa: F401  (registers the stub package)

from query_translation.oqo import OQO  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.validator import validate_oqo  # noqa: E402

_DOCS_OQL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs", "oql",
)
CORPUS_PATH = os.path.join(_DOCS_OQL, "corpus.yaml")
NL_EVAL_PATH = os.path.join(_DOCS_OQL, "nl_eval.yaml")


def _load_yaml(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def _load_corpus_golds():
    """Map corpus id -> gold OQO dict (only rows that carry an `oqo` oracle)."""
    return {r["id"]: r["oqo"] for r in _load_yaml(CORPUS_PATH)["rows"] if r.get("oqo")}


def _load_nl_cases():
    return _load_yaml(NL_EVAL_PATH).get("cases", [])


def _gold_oqo_for_case(case, corpus_golds):
    if "ref" in case:
        ref = case["ref"]
        if ref not in corpus_golds:
            raise KeyError(f"ref '{ref}' not found in corpus golds")
        return corpus_golds[ref]
    if "oqo" in case:
        return case["oqo"]
    raise KeyError("case has neither `ref` nor `oqo`")


def _case_id(case):
    return case.get("ref") or case.get("id") or "<unknown>"


def _canon_key(oqo):
    """Stable, hashable signature of an OQO's canonical form (the same Tier-1
    equality used by the grader: canonicalize(...).to_dict())."""
    return json.dumps(canonicalize_oqo(oqo).to_dict(), sort_keys=True)


CORPUS_GOLDS = _load_corpus_golds()
CASES = _load_nl_cases()

# canonical signature -> corpus id, for detecting standalone golds that are
# really a corpus row in disguise. Corpus golds are already round-trip-checked by
# test_corpus_roundtrip.py; skip any that fail to parse here rather than
# double-reporting their breakage in this suite.
CORPUS_CANON = {}
for _cid, _gold in CORPUS_GOLDS.items():
    try:
        CORPUS_CANON[_canon_key(OQO.from_dict(_gold))] = _cid
    except Exception:
        pass


def _validate_case(case):
    """Return a list of hard-failure error strings for one case (empty == ok)."""
    errors = []
    cid = _case_id(case)
    is_ref = "ref" in case
    is_standalone = "id" in case and "oqo" in case

    if not is_ref and not is_standalone:
        return [f"[{cid}] case is neither {{ref,nl}} nor {{id,oqo,nl}}"]
    if is_ref and "id" in case:
        errors.append(f"[{cid}] case has both `ref` and `id` — pick one")

    # standalone id must not collide with a corpus id (global uniqueness across
    # standalone ids is checked separately in test_standalone_ids_unique).
    if case.get("id") and case["id"] in CORPUS_GOLDS:
        errors.append(f"[{cid}] standalone id collides with corpus id '{case['id']}'")

    # nl block
    nl = case.get("nl")
    if not isinstance(nl, list) or not nl:
        errors.append(f"[{cid}] `nl` must be a non-empty list")
        nl = []
    for j, f in enumerate(nl):
        if not isinstance(f, dict) or "text" not in f or "difficulty" not in f:
            errors.append(f"[{cid}] nl[{j}] must be {{text, difficulty}}")
            continue
        if not str(f["text"]).strip():
            errors.append(f"[{cid}] nl[{j}] has empty text")
        if f["difficulty"] not in (1, 2, 3):
            errors.append(f"[{cid}] nl[{j}] difficulty {f['difficulty']!r} not in 1..3")

    if is_standalone and not case.get("provenance"):
        errors.append(f"[{cid}] standalone case must cite a `provenance` source")

    # gold OQO resolves + validates + canonicalizes
    try:
        gold_dict = _gold_oqo_for_case(case, CORPUS_GOLDS)
    except KeyError as e:
        return errors + [f"[{cid}] {e}"]
    try:
        oqo = OQO.from_dict(gold_dict)
    except Exception as e:
        return errors + [f"[{cid}] gold OQO failed to parse: {e}"]
    vr = validate_oqo(oqo)
    ok = vr.is_valid if hasattr(vr, "is_valid") else vr.to_dict().get("valid")
    if not ok:
        detail = vr.to_dict() if hasattr(vr, "to_dict") else vr
        return errors + [f"[{cid}] gold OQO is INVALID: {detail}"]
    try:
        ckey = _canon_key(oqo)
    except Exception as e:
        return errors + [f"[{cid}] gold OQO failed to canonicalize: {e}"]

    # inline-gold drift guard: a standalone gold identical (post-canonicalization)
    # to a corpus row should inherit it via `ref`, not copy it.
    if is_standalone:
        twin = CORPUS_CANON.get(ckey)
        if twin is not None:
            errors.append(
                f"[{cid}] standalone gold OQO is identical to corpus row "
                f"'{twin}' — use {{ref: {twin}}} instead of an inline copy"
            )
    return errors


def test_nl_eval_nonempty():
    assert CASES, "nl_eval.yaml has no `cases`"


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case_valid(case):
    """Per-case structural + gold-OQO validity + inline-drift checks."""
    errors = _validate_case(case)
    assert not errors, "; ".join(errors)


def test_standalone_ids_unique():
    """Standalone `id`s must be globally unique (order-independent, unlike a
    per-case running set)."""
    ids = [c["id"] for c in CASES if "id" in c]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    assert not dups, f"duplicate standalone ids: {dups}"


def test_coverage_gates():
    """Softer 'enough coverage' gates — distinct from the broken-data checks so a
    coverage shortfall reads differently from a malformed case."""
    n_corpus_rows = len(_load_yaml(CORPUS_PATH)["rows"])
    needed = -(-n_corpus_rows * 60 // 100)  # ceil(60% of all corpus rows)
    ref_rows_with_3plus = sum(
        1 for c in CASES if "ref" in c and isinstance(c.get("nl"), list) and len(c["nl"]) >= 3
    )
    standalone = sum(1 for c in CASES if "id" in c and "oqo" in c)
    assert ref_rows_with_3plus >= needed, (
        f"coverage: only {ref_rows_with_3plus} ref rows have >=3 NL formulations; "
        f"need >= {needed} (60% of {n_corpus_rows} corpus rows)"
    )
    assert standalone >= 10, f"only {standalone} standalone NL-only cases; need >= 10"
