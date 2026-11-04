"""Gaps from #1589's list, probed live 2026-11-04 (oxjob #1555).

`from` and `in` read either way for a place, an institution or a journal; other kinds of
link get a fix naming their own words; error fixes speak today's sentences.
"""
import pytest

from query_translation.oql_core import NotCore, parse_core, render_core
from query_translation.oql_parser import parse_either
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _same(a: str, b: str) -> bool:
    return canonicalize_oqo(parse_either(a)).to_dict() == canonicalize_oqo(parse_either(b)).to_dict()


@pytest.mark.parametrize("typed,canonical", [
    ("get works in [Austria](AT)", "get works from [Austria](AT)"),
    ("get works about kelp in [Austria](AT)", "get works about kelp from [Austria](AT)"),
    ("get works in [MIT](I63966007) about kelp", "get works from [MIT](I63966007) about kelp"),
    ("get works in [Africa](Q15)", "get works from [Africa](Q15)"),
    ("get works from [Nature](S137773608) about kelp", "get works about kelp in [Nature](S137773608)"),
    ("get the count of works in [Austria](AT) by year", "get the count of works from [Austria](AT) by year"),
])
def test_from_and_in_read_either_way(typed, canonical):
    assert _same(typed, canonical)


def test_the_echo_writes_the_canonical_word():
    assert render_core(canonicalize_oqo(parse_either("get works in [Austria](AT)"))) \
        == "get [Austria](AT)'s works"
    # a journal is `in` (the live echo adds its name from the resolver)
    assert render_core(canonicalize_oqo(parse_either("get works from [Nature](S137773608)"))) \
        == "get works in (S137773608)"


def test_works_listed_by_id_still_read():
    # today's grammar: a set of works by ID or a works collection after `get works in`
    oqo = parse_either("get works in (W2741809807, W2100837269)")
    (branch,) = oqo.filter_rows
    assert {f.column_id for f in branch.filters} == {"ids.openalex"}


@pytest.mark.parametrize("text,fix", [
    ("get works from [Springer](P4310319965) about kelp", "published by [Springer](P4310319965)"),
    ("get works in [NIH](F4320332161)", "funded by [NIH](F4320332161)"),
    ("get works from [Einstein](A5023888391)", "an author reads `by [Einstein](A5023888391)`"),
    ("get works in [Kelp forests](T10005)", "in the topic [Kelp forests](T10005)"),
])
def test_other_kinds_get_their_own_words(text, fix):
    with pytest.raises(NotCore) as e:
        parse_core(text)
    assert fix in e.value.fix


def test_a_split_by_corresponding_institution_is_a_sentence():
    # the general form wrote `get institutions that were corresponding institutions   of works ...`
    text = "get the count of works about kelp by corresponding institution"
    oqo = canonicalize_oqo(parse_either(text))
    assert [g.column_id for g in oqo.group_by] == ["corresponding_institution_ids"]
    assert render_core(oqo) == text


# --- error fixes speak today's sentences ------------------------------------------

def _error(text):
    from query_translation.diagnostics import OQLError
    with pytest.raises(OQLError) as e:
        parse_either(text)
    return e.value


def test_a_comparison_word_with_no_number_names_the_fix():
    e = _error("get works where citation count is above abc")
    assert e.message == 'a number goes after "above" for "citation count"'
    assert e.fixit == "e.g. citation count is above 100"


def test_no_fix_shows_the_retired_shapes():
    from query_translation.diagnostics import DIAGNOSTICS
    for code in ("OQL_TRAILING_TOKENS", "OQL_BAD_NUMBER", "OQL_UNKNOWN_STEP"):
        fix = DIAGNOSTICS[code].default_fixit
        assert "sample N" not in fix and "sample (N)" not in fix and "(2020)" not in fix, code


def test_a_step_after_a_sentence_says_a_table_is_one_sentence():
    with pytest.raises(NotCore) as e:
        parse_core("get the count of works about kelp; then group those works by year")
    assert "no steps now" not in str(e.value) and "by year`" in e.value.fix


def test_a_count_of_matching_works_on_a_list_says_both_fixes():
    # read Austria as a works ID; then today's grammar's "unexpected text" hid core's reason
    from query_translation.diagnostics import OQLError
    with pytest.raises(OQLError) as e:
        parse_either("get institutions with at least 500 works in [Austria](AT)")
    fix = getattr(e.value, "core_error").fix
    assert "`get institutions in [Austria](AT) with at least 500 works`" in fix
    assert ("`get the count of works in [Austria](AT) by institution. Only institutions with at "
            "least 500 works in [Austria](AT).`") in fix
    for text in ("get institutions in [Austria](AT) with at least 500 works",
                 "get the count of works in [Austria](AT) by institution. Only institutions with "
                 "at least 500 works in [Austria](AT)."):
        parse_either(text)
