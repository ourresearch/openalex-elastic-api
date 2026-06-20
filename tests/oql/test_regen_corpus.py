"""Regression tests for docs/oql/regen_corpus_oql.py (oxjob #497).

The rewriter used to key rewrites off a global `{id: row}` dict, which silently
collapsed duplicate ids (last-wins) and let one row's regenerated derived fields
land in a *different* row's text block — observed when #481 reused id 182, an
existing #363 `error` row, and the ok row's `oqo` was written into the error row.

The fix pairs text blocks to parsed rows POSITIONALLY and refuses to run on a
duplicate-id (or otherwise misaligned) corpus. These tests pin both properties:
an `error` row wedged between two `ok` rows stays byte-identical, and a duplicate
id raises instead of cross-writing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "docs", "oql"))
import regen_corpus_oql as regen  # noqa: E402


# A minimal, valid corpus: ok / error / ok, with the error row deliberately
# wedged between the two ok rows (the #497 layout). The ok rows carry a real,
# canonical oql + oqo so the rewriter actually recomputes their derived fields.
_OK_OQL = "works where it's open access"
_OK_OQO = ("{get_rows: works, filter_rows: [{column_id: open_access.is_oa, "
           "value: true}]}")


def _ok_block(row_id: int) -> str:
    return (
        f"- id: {row_id}\n"
        f"  tags: [filter]\n"
        f"  status: ok\n"
        f"  oxurl_status: has-oxurl\n"
        f"  oql: '{_OK_OQL.replace(chr(39), chr(39) * 2)}'\n"
        f"  oxurl: 'STALE-PLACEHOLDER'\n"
        f"  oqo: {_OK_OQO}\n"
    )


_ERROR_BLOCK = (
    "- id: 2\n"
    "  tags: [boolean-logic]\n"
    "  status: error\n"
    "  oql: 'works where type is any of (article, review)'\n"
    "  diagnostic: OQL_ANY_OF_RENAMED\n"
    "  note: 'this error row must never be touched by the rewriter'\n"
)

_PREAMBLE = "# fixture corpus\nrows:\n"


def _corpus(*blocks: str) -> list:
    return (_PREAMBLE + "".join(blocks)).splitlines(keepends=True)


def _blocks(lines: list) -> list:
    _, blocks = regen.split_blocks(lines)
    return blocks


def test_error_row_between_ok_rows_is_byte_untouched():
    """The error row sandwiched between two ok rows is returned byte-identical;
    each ok row gets its OWN recomputed derived fields (no cross-write)."""
    src = _corpus(_ok_block(1), _ERROR_BLOCK, _ok_block(3))
    out = regen.regenerate(src)

    in_blocks, out_blocks = _blocks(src), _blocks(out)
    assert len(out_blocks) == 3

    # The middle (error) block is unchanged, line for line.
    assert out_blocks[1] == in_blocks[1]
    # And specifically: its authored oql survives and no `oqo`/`corpus` leaked in.
    err_text = "".join(out_blocks[1])
    assert "works where type is any of (article, review)" in err_text
    assert "oqo:" not in err_text
    assert "corpus:" not in err_text

    # Both ok rows got their oxurl freshly rendered (placeholder gone), each in
    # its own block.
    for idx in (0, 2):
        ok_text = "".join(out_blocks[idx])
        assert "STALE-PLACEHOLDER" not in ok_text
        assert "open_access.is_oa" in ok_text


def test_duplicate_id_raises_rather_than_corrupts():
    """Two rows sharing an id is the exact #497 trigger — refuse, don't cross-write."""
    src = _corpus(_ok_block(2), _ERROR_BLOCK)  # both id 2
    with pytest.raises(ValueError, match=r"duplicate row id"):
        regen.regenerate(src)


def test_no_change_when_already_canonical():
    """Running twice is a no-op: the second pass must change nothing (idempotent)."""
    src = _corpus(_ok_block(1), _ERROR_BLOCK, _ok_block(3))
    once = regen.regenerate(src)
    twice = regen.regenerate(once)
    assert twice == once
