"""Value-domain validation: closed-vocab membership (oxjob #363).

Charter: OQL is *readable in form but strict in validation* — fuzzy / name-based
matching is the NL parser's job (#344); raw OQL must reject any value that isn't a
literal member of a closed code vocabulary. This catches the silent-garbage footgun
where `country is Canada` (→ value `CANADA`) or `country is 42` matched zero docs but
validated as OK.

The check is at the OQO VALIDATOR layer (not the parser): `country is Canada` parses
fine, then `validate_oqo` flags `invalid_value`. The membership set is the renderer's
`config/<vocab>.yaml` table (single source of truth — a value validates iff it can
also be rendered with a display name).

Pure: no app boot (core.properties imports without Flask). Run with
    PYTHONPATH=. pytest tests/oql/test_value_domain.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse as parse_oql  # noqa: E402
from query_translation.validator import validate_oqo, CLOSED_VOCAB_NAMESPACE  # noqa: E402
from query_translation.diagnostics import DIAGNOSTICS  # noqa: E402


def _errors(oql):
    """(type, message) for every validation error of an OQL string."""
    return [(e.type, e.message) for e in validate_oqo(parse_oql(oql)).errors]


def _invalid_value_errors(oql):
    return [m for (t, m) in _errors(oql) if t == "invalid_value"]


# --- valid members pass (one per Tier-1 closed vocab) ------------------------
@pytest.mark.parametrize("oql", [
    "works where country is ca",                  # countries (uppercased to CA)
    "works where country is GB",                  # GB is the United Kingdom's ISO code
    "works where language is en",                 # languages
    "works where sdg is 3",                       # sdgs (numeric id)
    "works where type is article",                # work-types
    "works where open access status is gold",     # oa-statuses
])
def test_valid_members_pass(oql):
    assert _invalid_value_errors(oql) == [], oql


# --- non-member names / garbage are rejected --------------------------------
@pytest.mark.parametrize("oql", [
    "works where country is Canada",              # a NAME, not a code
    "works where country is 42",                  # nonsense
    "works where country is uk",                  # UK is not ISO — it's GB
    "works where language is english",            # name, not code
    "works where sdg is 99",                      # out-of-range id
    "works where type is boguskind",
    "works where open access status is sparkly",
])
def test_non_members_rejected(oql):
    errs = _invalid_value_errors(oql)
    assert len(errs) == 1, f"{oql} -> {errs}"


# --- the footgun this subsumes: a name suggests its code (did-you-mean) ------
def test_country_name_suggests_code():
    [msg] = _invalid_value_errors("works where country is Canada")
    assert "Did you mean 'ca'?" in msg


def test_language_name_suggests_code():
    [msg] = _invalid_value_errors("works where language is english")
    assert "Did you mean 'en'?" in msg


# --- membership descends into boolean value groups (every leaf) --------------
def test_branch_group_validates_each_leaf():
    # `(us or canada)` — US ok, CANADA must be flagged (the bad leaf, not the good one)
    errs = _invalid_value_errors("works where country is (us or canada)")
    assert len(errs) == 1 and "CANADA" in errs[0]


def test_branch_group_all_valid_passes():
    assert _invalid_value_errors("works where country is (us or gb)") == []


# --- strict by decision: no name->code coercion happens, it's an error -------
def test_strict_no_auto_resolution():
    # `country is Canada` is an ERROR, never silently resolved to `ca`.
    assert _invalid_value_errors("works where country is Canada")


# --- non-vocab string columns are untouched (only entity_type vocabs gated) --
def test_free_text_search_value_not_membership_checked():
    # a title search value is open free text — never membership-checked.
    assert _invalid_value_errors('works where title contains "anything at all"') == []


def test_open_id_entity_not_membership_checked_here():
    # institutions are an open ID entity (millions) — Tier-2 ID-shape, not Tier-1
    # membership; a real institution id must not trip invalid_value.
    assert _invalid_value_errors("works where institution is I27837315") == []


# --- the diagnostic is registered so the editor gets a fix-it ----------------
def test_invalid_value_diagnostic_registered():
    spec = DIAGNOSTICS.get("invalid_value")
    assert spec is not None and spec.severity == "error"
    assert spec.default_fixit  # carries an actionable hint for the editor


# --- the map is the design's vetted Tier-1 set (guard against silent drift) --
def test_closed_vocab_namespace_set():
    assert set(CLOSED_VOCAB_NAMESPACE) == {
        "countries", "continents", "languages", "sdgs", "work-types", "oa-statuses",
    }
    # work-types' config namespace is the legacy "types"
    assert CLOSED_VOCAB_NAMESPACE["work-types"] == "types"
