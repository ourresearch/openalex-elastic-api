"""`invalid_column` "did you mean" suggestions (oxjob #423).

`invalid_column` pooled three different causes — an unregistered engine field, a
translator-built malformed column (wrong segment order, e.g. `<f>.exact.search`),
and a plain typo — under one low-information string. A near-miss suggestion makes
each self-diagnosing, mirroring the value-level suggestion already in
`_validate_closed_vocab`. The suggester is a pure function over the registry's
column ids; this locks its two tiers (segment-permutation, then edit-distance) and
the no-spurious-suggestion guarantee.

Pure: no app boot (core.properties imports without Flask). Run with
    PYTHONPATH=. pytest tests/oql/test_invalid_column_suggestions.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.validator import (  # noqa: E402
    _suggest_columns,
    get_entity_properties,
    validate_oqo,
)
from query_translation.oqo import OQO, LeafFilter  # noqa: E402


WORKS_COLS = list(get_entity_properties("works").keys())


def _invalid_column_msg(bad_id):
    """The invalid_column message for a works leaf with column `bad_id`."""
    oqo = OQO(get_rows="works", filter_rows=[LeafFilter(bad_id, "x", "is")])
    errs = [e for e in validate_oqo(oqo).errors if e.type == "invalid_column"]
    assert errs, f"expected invalid_column for {bad_id!r}"
    return errs[0].message


# --- the pure suggester ------------------------------------------------------

def test_segment_reorder_is_top_suggestion():
    # `<f>.exact.search` (the #422 translator footgun) -> canonical `<f>.search.exact`,
    # ranked ahead of the dropped-segment `<f>.search`.
    out = _suggest_columns("title_and_abstract.exact.search", WORKS_COLS)
    assert out[0] == "title_and_abstract.search.exact"
    assert "title_and_abstract.search" in out


def test_plain_typo_suggests_correct_column():
    assert _suggest_columns("pubilcation_year", WORKS_COLS)[0] == "publication_year"
    assert _suggest_columns("cited_by_cont", WORKS_COLS)[0] == "cited_by_count"


def test_no_suggestion_for_bogus_id():
    assert _suggest_columns("zzzzz", WORKS_COLS) == []


def test_no_spurious_suggestion_for_distant_id():
    # `citaton_count` is too far from any registered column (nearest real column is
    # `cited_by_count`, ratio 0.67) — suggest nothing rather than something wrong.
    assert _suggest_columns("citaton_count", WORKS_COLS) == []


def test_capped_at_two():
    assert len(_suggest_columns("title_and_abstract.exact.search", WORKS_COLS)) <= 2


def test_non_string_id_is_safe():
    assert _suggest_columns(None, WORKS_COLS) == []
    assert _suggest_columns(42, WORKS_COLS) == []


# --- wired into the validator message ----------------------------------------

def test_message_appends_did_you_mean_for_reorder():
    msg = _invalid_column_msg("title_and_abstract.exact.search")
    assert "Did you mean" in msg
    assert "title_and_abstract.search.exact" in msg


def test_message_has_no_did_you_mean_for_bogus():
    msg = _invalid_column_msg("zzzzz")
    assert "Did you mean" not in msg
    assert msg == "'zzzzz' is not a valid column."
