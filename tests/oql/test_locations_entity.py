"""Locations as a first-class entity — OQL column resolution (oxjob #850).

The locations entity's columns are plain fields on the locations index, but the
WORD `version` reaches the parser through the works raw-registry-column door
(works' `version` param is an alias of the nested `locations.version`), which
used to hand back the works Field UNresolved — so `locations where version is
publishedVersion` emitted column_id `locations.version` and the validator 400'd
it as invalid_column. Fixed 2026-08-30 by entity-resolving the fallback door's
Field by the TYPED word. These tests pin the entity-correct resolution and
freeze works' behavior.

Offline: engine + registry only, no app boot, no ES.
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402


def _columns(oqo):
    return [f.column_id for f in oqo.filter_rows] + [g.column_id for g in oqo.group_by]


@pytest.mark.parametrize(
    "oql,expected_columns",
    [
        # `version` must resolve to locations' own bare column, not works'
        # `locations.version` alias target (the pre-fix failure).
        ("locations where version is publishedVersion", ["version"]),
        ("locations group by version", ["version"]),
        # Words that resolve through the curated door, entity-corrected.
        ("locations where license is licenses/cc-by", ["license"]),
        ("locations where source is sources/S137773608", ["source_id"]),
        ("locations where language is languages/en", ["language"]),
    ],
)
def test_locations_words_resolve_to_locations_columns(oql, expected_columns):
    assert _columns(parse_oql_to_oqo(oql)) == expected_columns


@pytest.mark.parametrize(
    "oql,expected_columns",
    [
        # FROZEN: on works, `version` stays the works alias target.
        ("works where version is publishedVersion", ["locations.version"]),
        ("works group by version", ["locations.version"]),
    ],
)
def test_works_version_behavior_frozen(oql, expected_columns):
    assert _columns(parse_oql_to_oqo(oql)) == expected_columns


def test_locations_version_round_trips():
    """The resolved bare column must survive an OQL→OQO→OQL→OQO round trip
    (an entity-resolved column that renders to a word which re-parses to a
    DIFFERENT column would silently corrupt saved queries)."""
    from tests.oql.oql_v2 import render

    oqo = parse_oql_to_oqo("locations where version is publishedVersion")
    rendered = render(oqo)
    again = parse_oql_to_oqo(rendered)
    assert _columns(again) == _columns(oqo) == ["version"]
