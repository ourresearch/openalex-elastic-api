"""OQL reads and writes `pulled` (works is_pulled, oxjob #2264) the way it does `retracted`."""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

import pytest  # noqa: E402

from query_translation import oql_core as C  # noqa: E402
from query_translation.oql_lang import parse, render_tree  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402


def _leaf(oql):
    rows = canonicalize_oqo(parse(oql)).filter_rows
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("oql, value", [
    ("works where pulled is true", True),
    ("works where pulled is false", False),
    ("works where it's pulled", True),
    ("works where it's not pulled", False),
])
def test_parses_to_is_pulled(oql, value):
    leaf = _leaf(oql)
    assert leaf.column_id == "is_pulled"
    assert leaf.value is value


def test_round_trips():
    canon = canonicalize_oqo(parse("works where pulled is true"))
    out = render_tree(canon, resolver=None)[0]
    assert canonicalize_oqo(parse(out)).to_dict() == canon.to_dict()


def test_core_words():
    # "pulled works", "percent pulled" by year: Jason's share-over-time use (16 Nov 2026)
    assert C.ADJECTIVES["is_pulled"] == "pulled"
    assert C.MEASURE_NAMES[("percent", "is_pulled")] == "percent pulled"
    assert C.DIMS["is_pulled"] == "pulled"
