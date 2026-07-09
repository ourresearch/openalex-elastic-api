"""`oql_oneline` — single-line canonical OQL for the editor's live regroup (oxjob #587).

`render_v2_and_oql` now returns a third value: the always-single-line canonical
(`stringify` = `format_oql`'s pre-wrap `flat`). It has the SAME grouping /
parenthesization as the width-aware `oql` (multi-line past width 80), but NEVER inserts
line breaks or indent. The OQL editor rewrites its buffer to this live as you type, so a
user mixing `and`/`or` sees how we group things immediately; multi-line layout stays a
deliberate action on the tidy button.

Pure test — no Flask/ES. Run with:
    cd ~/Documents/openalex-elastic-api
    PYTHONPATH=. venv/bin/python -m pytest tests/oql/test_oql_oneline.py -q --noconftest
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from tests.oql.oql_v2 import parse  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.oql_render_v2 import render_v2_and_oql  # noqa: E402


def _render(oql: str):
    """Mirror the editor route (render_all_formats): canonicalize order-preserving
    (sort_operands=False, decision 30) then render. Returns (canonical, oneline)."""
    oqo = canonicalize_oqo(parse(oql), sort_operands=False)
    _tree, canonical, oneline = render_v2_and_oql(oqo)
    return canonical, oneline


def test_oneline_shows_precedence_grouping():
    # The headline case: mixed and/or inside a value group. The canonicalizer makes the
    # precedence explicit by adding the inner parens — WITHOUT reordering (order-preserving)
    # and WITHOUT line breaks. This is exactly what live regroup shows as you type.
    canonical, oneline = _render("works where title has (apple and banana or cherry)")
    assert oneline == "works where title has ((apple and banana) or cherry)"
    assert "\n" not in oneline
    # short enough to fit → the width-aware form is identical
    assert canonical == oneline


def test_oneline_always_parenthesizes_a_bare_value():
    # decision 39: a condition's value is always a parenthesized group.
    _canonical, oneline = _render("works where title has cat")
    assert oneline == "works where title has (cat)"
    assert "\n" not in oneline


def test_oneline_is_single_line_where_oql_wraps():
    # A query long enough to exceed the 80-col format width: `oql` (canonical) goes
    # multi-line; `oql_oneline` stays on one line with the SAME grouping.
    long_q = ("works where title has ((cat and dog) or bird) "
              "and abstract has (climate and change) and publication_year is 2020")
    canonical, oneline = _render(long_q)
    assert "\n" in canonical          # width-aware form wraps
    assert "\n" not in oneline        # single-line form never does
    # same query, just different whitespace/layout: both re-parse to the same OQO
    assert (canonicalize_oqo(parse(oneline), sort_operands=False).to_dict()
            == canonicalize_oqo(parse(canonical), sort_operands=False).to_dict())


def test_oneline_is_a_fixed_point():
    # Live regroup dispatches oql_oneline back into the buffer; re-validating must yield
    # the identical string (else the editor would oscillate keystroke-to-keystroke).
    _c, oneline1 = _render("works where title has (apple and banana or cherry)")
    _c2, oneline2 = _render(oneline1)
    assert oneline1 == oneline2
