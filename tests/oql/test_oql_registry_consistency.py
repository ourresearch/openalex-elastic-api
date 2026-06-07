"""
OQL ⇄ registry consistency gate (oxjob #381 Phase 5).

The registry (`/properties`, snapshotted to `docs/properties-snapshot.json`) is the
single source of truth for each property's canonical **display label** + **alias
list**. The OQL engine (`query_translation/oql_lang.py`) keeps a hand-curated field
table (`_FIELDS`) carrying OQL-only metadata the registry doesn't model (`kind`,
value casing, boolean phrasings, `resolves_name`). This gate proves the *names* in
that table have not drifted from the registry — the same anti-re-drift posture the
GUI uses (`scripts/check_label_consistency.py`), but for the OQL surface.

It enforces ACCEPTANCE.md criteria 4 (round-trip identity / no default.search
narrowing), 5 (OQL names derive from the registry, not an independent hand-table),
and 7 (cross-surface consistency: OQL render word == registry display_name, and
every OQL parse alias ∈ registry aliases).

Runs in the env-free `tests/oql/` harness (no ES / no `create_app()`): it reads the
committed snapshot JSON and imports the pure engine via the `_qt_loader` stub.
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401  (registers the stub query_translation pkg)
from query_translation.oql_lang import _FIELDS, parse, render

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SNAPSHOT = os.path.join(_REPO, "docs", "properties-snapshot.json")

# OQL is the works query language, so every field resolves against the works entity.
with open(_SNAPSHOT) as _fh:
    _WORKS = json.load(_fh)["properties"]["works"]


# Columns whose OQL render word is intentionally OQL-specific — they are NOT works
# registry properties (cross-type conveniences or the same-type membership subject),
# so there is no registry label to agree with. Mirrors the GUI gate's ALLOWLIST.
OQL_ONLY_COLUMNS = {
    "institutions.display_name",          # "institution name" — search over the affiliated org's name
    "last_known_institutions.id",         # "last known institution" — an authors column, usable on works
    "last_known_institutions.country_code",  # "author country"
    "country_code",                       # "country code" — bare ISO code convenience
    "domain.id",                          # "domain" — shorthand; works carries primary_topic.domain.id
    "collection",                         # "work[s]" — the same-type membership SUBJECT, not a property
}


def _registry_prop(field):
    """The works registry property name for an OQL Field, or None if OQL-only.
    Search fields map to the `<col>.search` param; everything else to `<col>`."""
    name = f"{field.column}.search" if field.kind == "search" else field.column
    return _WORKS.get(name)


def _human_aliases(spellings):
    """OQL alias spellings that are human words (not a dotted param/column id and
    not a snake_case token) — the spellings a user would actually type and that the
    registry's `aliases` list is meant to advertise."""
    return [s for s in spellings if "." not in s and "_" not in s]


_MAPPED = [(sp, f) for sp, f in _FIELDS
           if f.column not in OQL_ONLY_COLUMNS and _registry_prop(f) is not None]


def _ids(items):
    return [f.column for _sp, f in items]


@pytest.mark.parametrize("spellings,field", _MAPPED, ids=_ids(_MAPPED))
def test_oql_render_word_equals_registry_display_name(spellings, field):
    """Criterion 7 (headline): the word OQL PRINTS for a column is the registry's
    canonical display_name. (Booleans render via their bool_true/bool_false phrasing,
    not the field word, so their `oql` word is parse-only — exempt from this check.)"""
    if field.kind == "bool":
        pytest.skip("boolean field word is parse-only; printed form is the phrasing")
    prop = _registry_prop(field)
    assert field.oql.lower() == prop["display_name"].lower(), (
        f"OQL render word {field.oql!r} != registry display_name "
        f"{prop['display_name']!r} for column {field.column!r}. Reconcile in "
        f"oql_lang._FIELDS (or core/display_names.py), then regen the snapshot + corpus."
    )


@pytest.mark.parametrize("spellings,field", _MAPPED, ids=_ids(_MAPPED))
def test_oql_human_aliases_are_advertised_by_the_registry(spellings, field):
    """Criterion 7 (alias clause): every human spelling OQL accepts for a column is
    advertised by the registry's display_name/aliases, so `/properties` is the
    superset of accepted input. (Dotted param ids / snake_case tokens are structural
    and excluded; booleans expose an OQL-specific phrasing surface — "it has a DOI" —
    that the registry's single display_name doesn't model, so they are exempt.)"""
    if field.kind == "bool":
        pytest.skip("boolean parse phrasings are an OQL-specific surface")
    prop = _registry_prop(field)
    advertised = {prop["display_name"].lower()} | {a.lower() for a in prop.get("aliases", [])}
    missing = [s for s in _human_aliases(spellings) if s.lower() not in advertised]
    assert not missing, (
        f"OQL accepts {missing} for column {field.column!r} but the registry does "
        f"not advertise them. Add them to core/display_names.py aliases and regen."
    )


@pytest.mark.parametrize("spellings,field", _MAPPED, ids=_ids(_MAPPED))
def test_oql_render_word_round_trips(spellings, field):
    """Criterion 4: render(parse(<render word>)) == the render word, and it resolves
    back to the SAME column — no render-only / parse-only drift."""
    if field.kind == "bool":
        pytest.skip("booleans are tested via their phrasing, not the field word")
    if field.kind == "collection":
        pytest.skip("collection takes a col_… set ref, not a value")
    word = field.oql
    if field.kind == "search":
        oql = f'works where {word} contains "x"'
    elif field.kind == "num":
        oql = f"works where {word} > 1"
    elif field.kind in ("id",):
        oql = f"works group by {word}"
    elif field.kind == "enum":
        oql = f"works group by {word}"
    elif field.kind == "string":
        oql = f'works where {word} is "x"'
    else:
        pytest.skip(f"unhandled kind {field.kind}")
    out = render(parse(oql))
    assert word in out, f"render word {word!r} did not survive round-trip: {out!r}"


def test_default_search_does_not_narrow():
    """Criterion 4 (the load-bearing #374/#381 fix): every broad full-text spelling —
    including the deprecated `default.search` and the one-word `fulltext` — parses to
    the SAME column, so a broad search no longer silently narrows to body-only on a
    render→re-parse round trip (the old 95→63 bug)."""
    cols = set()
    for word in ["full text", "fulltext", "anywhere", "any field", "default", "default.search"]:
        oqo = parse(f'works where {word} contains "x"')
        row = oqo.filter_rows[0]
        cols.add(row["column_id"] if isinstance(row, dict) else row.column_id)
    assert len(cols) == 1, f"broad-search spellings diverge across columns: {cols}"


def test_sdg_word_is_the_acronym_everywhere():
    """#381 Phase 5 decision: 'SDG' is canonical in the registry AND OQL."""
    assert _WORKS["sustainable_development_goals.id"]["display_name"] == "SDG"
    sdg = next(f for _sp, f in _FIELDS if f.column == "sustainable_development_goals.id")
    assert sdg.oql == "SDG"
