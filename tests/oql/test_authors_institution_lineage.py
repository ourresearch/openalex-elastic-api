"""An author's last known institution includes its child organizations (oxjob #594, ticket 22523).

`last known institution is X` on authors means X and its labs and institutes
(`last_known_institutions.lineage`), as `institution is X` does on works and `at X` does on
authors: one meaning for "institution" everywhere. The id alone is `exact last known
institution` (works: `exact institution`). Old `last_known_institutions.id:` URLs keep their
exact meaning and echo with the exact word, so every URL round-trips.
"""
import pytest

from query_translation.analytics import _own_value_path
from query_translation.oql_core import parse_core, render_core
from query_translation.oql_lang import parse, render
from query_translation.url_parser import parse_url_to_oqo

LORRAINE = "I90183372"


def _col(oqo):
    return oqo.filter_rows[0].column_id


@pytest.mark.parametrize("q", [
    f"get authors where last known institution is ({LORRAINE})",
    f"get authors where institution is ({LORRAINE})",
    f"get authors at ({LORRAINE}) now",
])
def test_institution_on_authors_includes_child_organizations(q):
    o = parse(q)
    assert _col(o) == "last_known_institutions.lineage"
    assert render(o) == f"authors where last known institution is ({LORRAINE})"


@pytest.mark.parametrize("q", [
    f"get authors where exact last known institution is ({LORRAINE})",
    f"get authors where exact institution is ({LORRAINE})",
])
def test_exact_last_known_institution_is_the_id_alone(q):
    o = parse(q)
    assert _col(o) == "last_known_institutions.id"
    assert render(o) == f"authors where exact last known institution is ({LORRAINE})"


@pytest.mark.parametrize("flt,col,word", [
    (f"last_known_institutions.lineage:{LORRAINE}", "last_known_institutions.lineage",
     "last known institution"),
    (f"last_known_institutions.id:{LORRAINE}", "last_known_institutions.id",
     "exact last known institution"),
])
def test_urls_echo_oql_that_reads_back_the_same(flt, col, word):
    # before #594 the lineage URL echoed `last_known_institutions.lineage is (...)`, which
    # OQL refused ("unknown field")
    o = parse_url_to_oqo("authors", filter_string=flt)
    assert _col(o) == col
    echo = render(o)
    assert echo == f"authors where {word} is ({LORRAINE})"
    assert parse(echo).to_dict() == o.to_dict()


def test_a_split_by_author_filtered_on_the_last_known_institution_uses_lineage():
    text = f"get the count of works about kelp by author where last known institution is ({LORRAINE})"
    o = parse_core(text)
    assert o.group_by[0].where.column_id == "last_known_institutions.lineage"
    assert render_core(o) == text


def test_the_institution_shown_beside_each_author_is_the_institution_itself():
    o = parse("get works where year > (2020); then group those works by author; then summarize "
              "using count and last known institution")
    value = [m for m in o.calculate if m.measure == "value"][0]
    assert value.column_id == "last_known_institutions.lineage"
    # read from the record's `.id` (its name), not the ids of its parents
    fields = {"last_known_institutions.lineage": object(), "last_known_institutions.id": object(),
              "summary_stats.h_index": object()}
    assert _own_value_path("last_known_institutions.lineage", fields) == "last_known_institutions.id"
    assert _own_value_path("summary_stats.h_index", fields) == "summary_stats.h_index"
    assert _own_value_path("x.lineage", {"x.lineage": 1}) == "x.lineage"
