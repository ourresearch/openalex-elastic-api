"""Multi-error recovery for the editor's `/validate` (oxjob #363, charter decision 15).

`parse_collecting()` is the second dual mode of the hand parser (alongside the
`_ctx_mode` cursor-context mode): it recovers at clause/operand and list-element
boundaries to report EVERY parse error in a doc, not just the first, so the editor can
squiggle the whole document. These tests lock that behavior AND the discipline that
keeps strict `parse()` byte-identical (recovery lives entirely behind `_recover_mode`).

Pure: no app boot. Run with
    PYTHONPATH=. pytest tests/oql/test_recover.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import (  # noqa: E402
    parse, parse_collecting, OQLError,
)
from query_translation.diagnostics import DIAGNOSTICS  # noqa: E402


def codes(q):
    _oqo, diags = parse_collecting(q)
    return [d.code for d in diags]


# --- the core win: every clause-level error is collected, not just the first ---
def test_two_unknown_fields_both_reported():
    diags = parse_collecting(
        "works where bogusfield is 1 and year is 2020 and otherbogus is 2")[1]
    assert [d.code for d in diags] == ["OQL_UNKNOWN_FIELD", "OQL_UNKNOWN_FIELD"]
    # positions point at each offending field, in source order
    assert [d.position for d in diags] == sorted(d.position for d in diags)
    assert diags[0].position < diags[1].position


def test_two_bad_values_both_reported():
    assert codes("works where year is abc or cited_by_count is xyz") == [
        "OQL_BAD_NUMBER", "OQL_BAD_NUMBER"]


def test_error_in_each_branch_of_a_group():
    # recovery descends into parenthesized groups (depth-tracked synchronize)
    assert codes("works where year >= 2020 and (bad1 is 1 or bad2 is 2)") == [
        "OQL_UNKNOWN_FIELD", "OQL_UNKNOWN_FIELD"]


def test_group_operand_recovery_collects_each_bad_element():
    # a value group `is (a or b or ...)` recovers at each operand boundary (#363)
    assert codes("works where year is (2020 or abc or 2021 or xyz)") == [
        "OQL_BAD_NUMBER", "OQL_BAD_NUMBER"]


def test_adjacency_is_recorded_then_next_clause_still_parses():
    # missing AND/OR between two clauses: record the adjacency, keep going
    diags = parse_collecting("works where year is abc title has")[1]
    got = [d.code for d in diags]
    assert "OQL_IMPLICIT_ADJACENCY" in got
    assert "OQL_BAD_NUMBER" in got  # the clause before the adjacency still reported


def test_unbalanced_parens_collected_alongside_inner_errors():
    diags = parse_collecting(
        "works where (year is abc and cited_by_count is def")[1]
    got = [d.code for d in diags]
    assert got.count("OQL_BAD_NUMBER") == 2
    assert "OQL_UNBALANCED_PARENS" in got


def test_mixed_bool_recovers_without_a_mixed_bool_diagnostic():
    # mixed AND/OR is no longer an error (#506): it resolves by precedence
    # (AND > OR), so recovery collects only the genuine errors around it and
    # never emits OQL_MIXED_BOOL_NEEDS_PARENS (a retired code).
    diags = parse_collecting(
        "works where bogus1 is 1 and year is 2020 or bogus2 is 2")[1]
    got = [d.code for d in diags]
    assert got.count("OQL_UNKNOWN_FIELD") == 2
    assert "OQL_MIXED_BOOL_NEEDS_PARENS" not in got


# --- every recovered diagnostic is a registered code (registry lockstep) -------
@pytest.mark.parametrize("q", [
    "works where bogusfield is 1 and otherbogus is 2",
    "works where year is abc or cited_by_count is xyz",
    "works where year is (2020 or abc or xyz)",
    "works where (year is abc and cited_by_count is def",
    "works where year is abc title has cat",
])
def test_collected_codes_are_registered(q):
    for d in parse_collecting(q)[1]:
        assert d.code in DIAGNOSTICS, f"unregistered recovery code {d.code!r}"


# --- the dual-mode discipline: strict parse() is untouched --------------------
def test_valid_query_recovers_clean_and_builds_oqo():
    oqo, diags = parse_collecting("works where year >= 2020 and type is article")
    assert diags == []
    assert oqo is not None and oqo.get_rows == "works"


def test_strict_parse_is_still_fail_fast():
    # the recover path must not bleed into strict parse: it still raises the FIRST
    # error and stops (only one error is observable)
    with pytest.raises(OQLError) as ei:
        parse("works where bogus1 is 1 and bogus2 is 2")
    assert ei.value.code == "OQL_UNKNOWN_FIELD"
    assert "bogus1" in ei.value.message


def test_empty_and_lexer_errors_match_strict_single_diagnostic():
    # no tokens to recover across -> a single diagnostic, same code strict raises
    assert codes("") == ["OQL_EMPTY"]
    assert codes('works where title has "open') == ["OQL_UNTERMINATED_STRING"]


def test_collecting_never_raises_on_pathological_input():
    # forward-progress guards must guarantee termination + no escaping exception
    for q in ["((((", "and and and", "works where ) ) )",
              "works where is is is", "works where ,,,,"]:
        oqo, diags = parse_collecting(q)  # must return, not hang or raise
        assert isinstance(diags, list)
