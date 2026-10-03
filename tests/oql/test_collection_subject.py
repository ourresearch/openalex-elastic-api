"""Same-type collection membership names the queried entity (oxjob #1524).

`locations where location is in collection (col_x)`, `authors where author is in
collection (col_x)`: the subject is the entity's singular display name (the entity
registry's `displayNameSingular`, the word the website's filter label uses). It
renders that way and reparses to the same `collection` leaf. `work is in collection`
was the only subject before, on every entity, so it stays accepted input everywhere.
On works, `author is in collection` is still the cross-type authors filter.

Run with:
    PYTHONPATH=. pytest tests/oql/test_collection_subject.py -q
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation.oql_lang import parse, render  # noqa: E402


def _leaves(oqo):
    return [(f.column_id, f.value, f.is_negated) for f in oqo.filter_rows]


@pytest.mark.parametrize("entity,subject", [
    ("works", "work"), ("authors", "author"), ("locations", "location"),
    ("institutions", "institution"), ("sources", "source"),
    ("types", "work type"), ("oa-statuses", "Open Access status"),
])
def test_subject_renders_and_round_trips(entity, subject):
    oql = f"{entity} where {subject} is in collection (col_ab1)"
    oqo = parse(oql)
    assert _leaves(oqo) == [("collection", "col_ab1", False)]
    assert render(oqo) == oql
    assert render(parse(render(oqo))) == oql


@pytest.mark.parametrize("entity", ["authors", "locations", "sources"])
def test_old_work_subject_still_parses(entity):
    oqo = parse(f"{entity} where work is in collection (col_ab1)")
    assert _leaves(oqo) == [("collection", "col_ab1", False)]


def test_negation_and_case():
    oqo = parse("locations where Location is not in collection (col_ab1)")
    assert _leaves(oqo) == [("collection", "col_ab1", True)]
    assert render(oqo) == "locations where location is in collection (not col_ab1)"


def test_cross_type_on_works_unchanged():
    oqo = parse("works where work is in collection (col_w) and author is in collection (col_a)")
    assert _leaves(oqo) == [("collection", "col_w", False), ("authorships.author.id", "col_a", False)]
