"""oxjob #331 Phase 3 — unit tests for the CI drift gate's bump classifier
(ACCEPTANCE Test 4: the gate enforces the bump rule).

These exercise the PURE classification logic in `scripts/classify_properties_diff.py`
against hand-built snapshot pairs — no app boot, no ES, no git. They pin the
mechanical bump rule (docs/PROPERTIES_VERSIONING.md):
  - additive (entity/property/operator/action added)        → MINOR
  - removal / type change / entity_type change / op|action  → MAJOR
  - rename (= remove + add)                                  → MAJOR
  - exact version-delta match required (under- AND over-bump FAIL)

Run with `pytest --noconftest` — the top-level conftest eagerly imports the app;
this test only needs the stdlib-only classifier on sys.path.
"""
import importlib.util
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MOD_PATH = os.path.join(_REPO_ROOT, "scripts", "classify_properties_diff.py")
_spec = importlib.util.spec_from_file_location("classify_properties_diff", _MOD_PATH)
clf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clf)


def _prop(type_="string", operators=("eq",), actions=("filter",), entity_type=None):
    return {
        "type": type_,
        "operators": list(operators),
        "actions": list(actions),
        "entity_type": entity_type,
    }


def _snapshot(version, properties):
    return {"meta": {"version": version}, "properties": properties}


BASE_PROPS = {
    "works": {
        "publication_year": _prop("number", ["eq", "gt"], ["filter", "sort"]),
        "open_access.is_oa": _prop("boolean", ["eq"], ["filter"]),
    },
    "authors": {
        "id": _prop("openalex_id", ["eq"], ["filter"], entity_type="authors"),
    },
}


# --------------------------------------------------------------------------- #
# classify_change — the content diff
# --------------------------------------------------------------------------- #

def test_no_change_is_none():
    cls, reasons = clf.classify_change(
        _snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", BASE_PROPS)
    )
    assert cls == "none"
    assert reasons == []


def test_added_property_is_minor():
    new = {**BASE_PROPS, "works": {**BASE_PROPS["works"], "title": _prop("string")}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "minor"
    assert any("property added: works.title" in r for r in reasons)


def test_added_entity_is_minor():
    new = {**BASE_PROPS, "sources": {"id": _prop("openalex_id")}}
    cls, _ = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "minor"


def test_added_operator_is_minor():
    new = {**BASE_PROPS, "works": {**BASE_PROPS["works"],
           "open_access.is_oa": _prop("boolean", ["eq", "not"], ["filter"])}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "minor"
    assert any("operator added: works.open_access.is_oa: not" in r for r in reasons)


def test_added_action_is_minor():
    new = {**BASE_PROPS, "works": {**BASE_PROPS["works"],
           "open_access.is_oa": _prop("boolean", ["eq"], ["filter", "group_by"])}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "minor"
    assert any("action added: works.open_access.is_oa: group_by" in r for r in reasons)


def test_removed_property_is_major():
    new = {**BASE_PROPS, "works": {"publication_year": BASE_PROPS["works"]["publication_year"]}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"
    assert any("property removed: works.open_access.is_oa" in r for r in reasons)


def test_removed_entity_is_major():
    new = {"works": BASE_PROPS["works"]}
    cls, _ = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"


def test_type_change_is_major():
    new = {**BASE_PROPS, "works": {**BASE_PROPS["works"],
           "publication_year": _prop("string", ["eq", "gt"], ["filter", "sort"])}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"
    assert any("type changed: works.publication_year" in r for r in reasons)


def test_entity_type_change_is_major():
    new = {**BASE_PROPS, "authors": {"id": _prop("openalex_id", ["eq"], ["filter"], entity_type="institutions")}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"
    assert any("entity_type changed: authors.id" in r for r in reasons)


def test_removed_operator_is_major():
    new = {**BASE_PROPS, "works": {**BASE_PROPS["works"],
           "publication_year": _prop("number", ["eq"], ["filter", "sort"])}}
    cls, _ = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"


def test_rename_is_major():
    # A rename surfaces as one removal + one addition; the removal forces MAJOR.
    new = {**BASE_PROPS, "works": {**{k: v for k, v in BASE_PROPS["works"].items()
                                       if k != "publication_year"},
                                    "pub_year": _prop("number", ["eq", "gt"], ["filter", "sort"])}}
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"
    assert any("property removed: works.publication_year" in r for r in reasons)


def test_major_dominates_when_both_added_and_removed():
    new = {**BASE_PROPS, "works": {"publication_year": BASE_PROPS["works"]["publication_year"],
                                    "title": _prop("string")}}  # removed is_oa, added title
    cls, reasons = clf.classify_change(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", new))
    assert cls == "major"
    # MAJOR reasons listed first, MINOR appended for context
    assert "property removed: works.open_access.is_oa" in reasons[0]


# --------------------------------------------------------------------------- #
# classify_version_delta
# --------------------------------------------------------------------------- #

def test_version_delta_classes():
    assert clf.classify_version_delta("1.0.0", "1.0.0") == "none"
    assert clf.classify_version_delta("1.0.0", "1.1.0") == "minor"
    assert clf.classify_version_delta("1.4.0", "2.0.0") == "major"
    # non-canonical moves
    assert clf.classify_version_delta("1.0.0", "1.0.1") == "invalid"   # patch lane
    assert clf.classify_version_delta("1.0.0", "3.0.0") == "invalid"   # skipped major
    assert clf.classify_version_delta("1.4.0", "2.1.0") == "invalid"   # major didn't reset minor
    assert clf.classify_version_delta("1.1.0", "1.0.0") == "invalid"   # decrease


# --------------------------------------------------------------------------- #
# check_bump — the full gate decision (exact-match policy)
# --------------------------------------------------------------------------- #

def _added(props):
    return {**props, "works": {**props["works"], "title": _prop("string")}}


def test_bump_minor_change_minor_version_passes():
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.1.0", _added(BASE_PROPS)))
    assert ok, msg


def test_bump_minor_change_no_bump_fails():
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", _added(BASE_PROPS)))
    assert not ok
    assert "MINOR" in msg


def test_bump_major_change_minor_bump_fails():
    removed = {"works": BASE_PROPS["works"]}  # dropped authors entity = MAJOR
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.1.0", removed))
    assert not ok
    assert "MAJOR" in msg


def test_bump_major_change_major_bump_passes():
    removed = {"works": BASE_PROPS["works"]}
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("2.0.0", removed))
    assert ok, msg


def test_bump_overbump_minor_change_major_version_fails():
    # Over-declaring breakage is still wrong — exact match keeps version honest.
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("2.0.0", _added(BASE_PROPS)))
    assert not ok


def test_bump_no_change_no_version_change_passes():
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.0.0", BASE_PROPS))
    assert ok, msg


def test_bump_spurious_version_change_fails():
    # version moved but content identical → fail (version moves iff content moves)
    ok, msg = clf.check_bump(_snapshot("1.0.0", BASE_PROPS), _snapshot("1.1.0", BASE_PROPS))
    assert not ok
    assert "unchanged" in msg
