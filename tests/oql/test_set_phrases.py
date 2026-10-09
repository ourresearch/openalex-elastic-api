"""Sets read `in the set (works where ...)` (oxjob #1555, Jason 2026-10-08): the query
in the parentheses is a phrase with no `get` and no article. Old forms stay accepted."""
import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(q):
    return canonicalize_oqo(parse(q))


def _line(q):
    return render_pipeline_line(_canon(q))


@pytest.mark.parametrize("canonical,older", [
    ("get works where it cites a work in the set (works where institution is (I146416000))",
     "get works where it cites works in (get works where institution is (I146416000))"),
    ("get works where it doesn't cite any work in the set (works where published in 2020)",
     "get works where it does not cite works in (get works where published in (2020))"),
    ("get works where it's cited by a work in the set (works where institution is "
     "(I146416000) and published in 2024)",
     "get works where it's cited by works in (get works where institution is (I146416000) "
     "and published in (2024))"),
    ("get works where author is in the set (authors of works where title-abstract has "
     "(kelp)) and published since 2025",
     "get works where author is in (get works where title-abstract has (kelp); then get "
     "authors of those works) and year >= (2025)"),
    ("get works where institution is not in the set (institutions of works where title "
     "has (kelp))",
     "get works where institution is not in (get works where title has (kelp); then get "
     "institutions of those works)"),
    ("get works where topic is in the collection (col_abc123)",
     "get works where topic is in (col_abc123)"),
    ("get works where it cites a work in the collection (col_abc123)",
     "get works where it cites works in (col_abc123)"),
])
def test_set_phrase_is_canonical_and_old_forms_read_the_same(canonical, older):
    assert _line(canonical) == canonical
    assert _line(older) == canonical
    assert _canon(older).to_dict() == _canon(canonical).to_dict()


@pytest.mark.parametrize("q", [
    "get works where it cites any work in the set (the works where published in 2020)",
    "get works where it cites works in set (works where published in 2020)",
    "get works where it cites a work in (works where published in 2020)",
])
def test_permissive_set_wording(q):
    assert _line(q) == "get works where it cites a work in the set (works where published in 2020)"


def test_walk_back_in_a_set():
    q = ("get works where it cites a work in the set (works of authors where h-index > 50)")
    o = _canon(q)
    inner = o.filter_rows[0].value
    assert inner.get_rows == "authors" and inner.walks[0].to == "works"
    assert _line(q) == q


def test_a_set_names_its_things():
    with pytest.raises(OQLError) as e:
        parse("get works where author is in the set (people of works where published in 2020)")
    assert e.value.code == "OQL_BAD_SET_PHRASE"
