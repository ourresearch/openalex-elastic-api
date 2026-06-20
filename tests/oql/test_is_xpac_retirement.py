"""#498 — soft-retire the `is_xpac` works filter, folding it into the #481 `corpus`
selector.

Two halves, both offline (no DB/ES):

1. REDIRECT — a TOP-LEVEL `is_xpac` leaf is translated to `corpus` at every OQO
   construction boundary (URL parse, `from_dict`, and the canonicalizer), so old
   callers keep working but the canonical OQO carries `corpus`, never the filter.
   `is_xpac:true → expansion`, `is_xpac:false → core`, negation flips it. Plus the
   #481 leftover: `?include_xpac=true → corpus="all"`, with an explicit `is_xpac:`
   filter winning over it (legacy precedence).

2. UNLISTED — `is_xpac` is dropped from the PUBLIC `/properties` catalog (it's
   `unlisted`) yet stays a LIVE, resolvable column in `ENTITY_PROPERTIES` (so the
   legacy REST filter path + validator + `?select=is_xpac` keep working).
"""

import json
import os

import pytest

from query_translation.oqo import (
    OQO,
    LeafFilter,
    BranchFilter,
    canonicalize_oqo_column_ids,
    redirect_is_xpac_to_corpus,
)
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.url_parser import parse_url_to_oqo


def _has_xpac_leaf(oqo):
    return any(getattr(f, "column_id", None) == "is_xpac" for f in oqo.filter_rows)


# --------------------------------------------------------------------------- #
# 1. Redirect parity
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("filt,expected", [
    ("is_xpac:true", "expansion"),
    ("is_xpac:false", "core"),
    ("is_xpac:!true", "core"),       # !true ≡ false → core
    ("is_xpac:!false", "expansion"),  # !false ≡ true → expansion
])
def test_url_is_xpac_redirects_to_corpus(filt, expected):
    oqo = parse_url_to_oqo("works", filter_string=filt)
    assert oqo.corpus == expected
    assert not _has_xpac_leaf(oqo), "the is_xpac leaf must be dropped after redirect"


def test_from_dict_redirects_bool_value():
    oqo = OQO.from_dict({
        "get_rows": "works",
        "filter_rows": [{"column_id": "is_xpac", "value": True}],
    })
    assert oqo.corpus == "expansion"
    assert not _has_xpac_leaf(oqo)


def test_redirect_is_idempotent():
    once = parse_url_to_oqo("works", filter_string="is_xpac:true")
    twice = redirect_is_xpac_to_corpus(once)
    assert twice.corpus == "expansion"
    assert not _has_xpac_leaf(twice)


def test_redirect_keeps_sibling_filters():
    oqo = parse_url_to_oqo("works", filter_string="is_xpac:true,is_oa:true")
    assert oqo.corpus == "expansion"
    assert not _has_xpac_leaf(oqo)
    # the other filter survives (canonicalized to its identity)
    remaining = {f.column_id for f in oqo.filter_rows}
    assert "open_access.is_oa" in remaining


def test_non_works_entity_passes_through():
    # `corpus` is works-only; an is_xpac leaf on another entity is left untouched
    oqo = parse_url_to_oqo("authors", filter_string="is_xpac:true")
    assert oqo.corpus == "core"
    assert _has_xpac_leaf(oqo)


def test_nested_is_xpac_branch_not_redirected():
    # An is_xpac inside an OR branch is not a corpus *selection* — leave it as a
    # plain term filter (the column survives internally).
    oqo = canonicalize_oqo_column_ids(OQO(
        get_rows="works",
        filter_rows=[BranchFilter(join="or", filters=[
            LeafFilter(column_id="is_xpac", value="true"),
            LeafFilter(column_id="is_retracted", value="true"),
        ])],
    ))
    assert oqo.corpus == "core"  # unchanged
    # the nested is_xpac leaf is still present somewhere in the tree
    branch = oqo.filter_rows[0]
    assert any(getattr(f, "column_id", None) == "is_xpac" for f in branch.filters)


def test_canonicalizer_path_also_redirects():
    raw = OQO(get_rows="works",
              filter_rows=[LeafFilter(column_id="is_xpac", value="false")])
    out = canonicalize_oqo(raw)
    assert out.corpus == "core"
    assert not _has_xpac_leaf(out)


# --------------------------------------------------------------------------- #
# include_xpac → corpus=all (#481 leftover), with filter precedence
# --------------------------------------------------------------------------- #

def test_include_xpac_maps_to_all():
    assert parse_url_to_oqo("works", include_xpac=True).corpus == "all"
    assert parse_url_to_oqo("works", include_xpac=False).corpus == "core"


@pytest.mark.parametrize("filt,expected", [
    ("is_xpac:true", "expansion"),
    ("is_xpac:false", "core"),
])
def test_explicit_is_xpac_filter_beats_include_xpac(filt, expected):
    oqo = parse_url_to_oqo("works", filter_string=filt, include_xpac=True)
    assert oqo.corpus == expected  # explicit filter wins over include_xpac


# --------------------------------------------------------------------------- #
# 2. Unlisted: gone from the public catalog, still live internally
# --------------------------------------------------------------------------- #

def test_is_xpac_absent_from_public_properties():
    from core.properties import render_properties
    works = render_properties("works")["properties"]
    assert "is_xpac" not in works


def test_is_xpac_still_live_in_catalog():
    # Soft-deprecation: the column stays resolvable for the validator / legacy
    # REST filter path / ?select=is_xpac — `unlisted` is a catalog HIDE, not a
    # functional removal.
    from core.properties import ENTITY_PROPERTIES, get_property
    assert "is_xpac" in ENTITY_PROPERTIES["works"]
    assert ENTITY_PROPERTIES["works"]["is_xpac"].unlisted is True
    assert get_property("works", "is_xpac") is not None


def test_snapshot_has_no_is_xpac():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    snap = json.load(open(os.path.join(repo_root, "docs", "properties-snapshot.json")))
    assert "is_xpac" not in snap["properties"].get("works", {})
