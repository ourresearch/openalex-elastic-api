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


# --- the map is the design's vetted Tier-1 (+1.5) set (guard against drift) ---
def test_closed_vocab_namespace_set():
    assert set(CLOSED_VOCAB_NAMESPACE) == {
        "countries", "continents", "languages", "sdgs", "work-types", "oa-statuses",
        # Tier-1.5 topic-hierarchy vocabs (oxjob #363):
        "domains", "fields", "subfields",
    }
    # work-types' config namespace is the legacy "types"
    assert CLOSED_VOCAB_NAMESPACE["work-types"] == "types"
    # the three Tier-1.5 vocabs are identity-mapped (namespace == entity_type)
    for ns in ("domains", "fields", "subfields"):
        assert CLOSED_VOCAB_NAMESPACE[ns] == ns


# =============================================================================
# Tier 1.5 — topic-hierarchy code vocabs (fields / subfields / domains).
#
# Same shape as Tier 1: small fully-enumerable closed sets backed by
# config/*.yaml. `field is 99999` (out-of-range) and `field is medicine` (a
# NAME) must be hard `invalid_value`, not silently valid. (oxjob #363.)
# =============================================================================

# --- valid members pass (friendly surface word + raw column) -----------------
@pytest.mark.parametrize("oql", [
    "works where field is 27",                    # primary_topic.field.id (Medicine)
    "works where subfield is 2712",               # primary_topic.subfield.id
    "works where topics.domain.id is 2",          # a domains-typed column (Social Sciences)
])
def test_tier15_valid_members_pass(oql):
    assert _invalid_value_errors(oql) == [], oql


# --- out-of-range ids and names are rejected ---------------------------------
@pytest.mark.parametrize("oql", [
    "works where field is 99999",                 # out-of-range field id
    "works where subfield is 99999",              # out-of-range subfield id
    "works where topics.domain.id is 99999",      # out-of-range domain id
])
def test_tier15_out_of_range_rejected(oql):
    errs = _invalid_value_errors(oql)
    assert len(errs) == 1, f"{oql} -> {errs}"


# --- a display name suggests its code (the footgun, did-you-mean) ------------
def test_tier15_field_name_suggests_code():
    [msg] = _invalid_value_errors("works where field is medicine")
    assert "Did you mean '27'?" in msg


# =============================================================================
# Tier 2 — OpenAlex-ID shape/prefix for open ID entities (oxjob #363).
#
# An `openalex_id`-typed value must carry the right entity prefix. `institution
# is W5` (a Works ID) is a hard `invalid_value`. The shape is the entity
# registry's `idRegex` (config/<entity>.yaml) — see core/entities.py.
# =============================================================================
from core.entities import get_entity_type, native_id_entities  # noqa: E402
from core.properties import get_entity_properties  # noqa: E402


# --- right-shaped ids for the right entity pass ------------------------------
@pytest.mark.parametrize("oql", [
    "works where institution is I27837315",       # I = institutions
    "works where author is A5023888391",          # A = authors
    "works where source is S137773608",           # S = sources
    "works where funder is F4320332161",          # F = funders
    "works where topic is T10017",                # T = topics
    "works where publisher is P4310320990",       # P = publishers
])
def test_tier2_correct_prefix_passes(oql):
    assert _invalid_value_errors(oql) == [], oql


# --- a right-shaped id of the WRONG entity is rejected -----------------------
@pytest.mark.parametrize("oql", [
    "works where institution is W5",              # W is Works, not Institutions
    "works where author is I5",                   # I is Institutions, not Authors
    "works where funder is W5",                   # W is Works, not Funders
    "works where source is A5",                   # A is Authors, not Sources
])
def test_tier2_wrong_prefix_rejected(oql):
    errs = _invalid_value_errors(oql)
    assert len(errs) == 1, f"{oql} -> {errs}"


# --- a non-id value on an id column is also rejected (no shape at all) --------
def test_tier2_non_id_value_rejected():
    errs = _invalid_value_errors("works where institution is Canada")
    assert len(errs) == 1 and "I" in errs[0]


# --- the fix-it names the wrong type when the value IS another entity's id ----
def test_tier2_wrong_type_fixit():
    [msg] = _invalid_value_errors("works where institution is W5")
    assert "is an OpenAlex works ID" in msg
    assert "institutions IDs start with 'I'" in msg


# --- `is in collection` (a different operator) is NOT shape-checked -----------
def test_tier2_collection_membership_not_shape_checked():
    # cross-type collection membership keeps the id column but uses the
    # `in collection` operator — Tier-2 fires only on `is`, so a `col_…` value
    # must not trip invalid_value.
    oql = "works where institution is in collection col_AbCdEf1234"
    assert _invalid_value_errors(oql) == [], oql


# --- COVERAGE GUARD: every open-ID column on /works resolves to a native-ID
#     entity in the registry, so none silently skips Tier-2 (catches a future
#     entity registered with no/!native idRegex, or a renamed entity_type). -----
def test_tier2_every_openalex_id_column_has_a_native_entity():
    missing = []
    for name, prop in get_entity_properties("works").items():
        if prop.type == "openalex_id" and prop.entity_type:
            ent = get_entity_type(prop.entity_type)
            if ent is None or not ent.is_native_id:
                missing.append((name, prop.entity_type))
    assert not missing, (
        "openalex_id columns whose entity has no native idRegex (Tier-2 would "
        f"silently skip them): {missing}"
    )


# --- the registry derives its native set + prefixes from config idRegex ------
def test_native_entities_and_prefixes():
    natives = native_id_entities()
    # the nine open OpenAlex-ID entities (continents also carries a Q-prefix id
    # but is a closed vocab handled by Tier-1, not openalex_id-typed).
    for entity, prefix in [
        ("works", "W"), ("authors", "A"), ("institutions", "I"), ("sources", "S"),
        ("publishers", "P"), ("funders", "F"), ("topics", "T"),
        ("concepts", "C"), ("awards", "G"),
    ]:
        assert entity in natives, entity
        assert natives[entity].id_prefix == prefix, entity
    # slug / numeric-id / closed-vocab entities are NOT native-id
    for entity in ["keywords", "countries", "languages", "fields", "domains"]:
        ent = get_entity_type(entity)
        assert ent is not None and not ent.is_native_id, entity
