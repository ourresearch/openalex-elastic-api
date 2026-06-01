"""Round-trip tests for the OQO logistics layer (#318).

Covers the four logistics additions that let an OQO fully stand in for an
OXURL on the `/:entity` endpoints: column projection (`select`), reproducible
sampling (`sample` + `seed`), and pagination (`per_page` / `page` / `cursor`).

Asserts:
  - `to_dict(from_dict(x)) == x` for OQOs carrying each new field (no loss).
  - back-compat: an OQO without any logistics field round-trips unchanged.
  - URL → OQO parsing maps `select` / `seed` / `per-page` / `page` / `cursor`
    onto the new OQO fields, and `render_oqo_to_url` reproduces them.
  - the canonicalizer passes the logistics fields through (no default injection).

Run with `pytest --noconftest` — the top-level conftest eagerly imports the app.
"""

import pytest

from query_translation.oqo import OQO
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import render_oqo_to_url
from query_translation.oqo_canonicalizer import canonicalize_oqo


# --- from_dict / to_dict round-trip ------------------------------------------

ROUND_TRIP_DICTS = {
    "back_compat_no_logistics": {"get_rows": "works"},
    "back_compat_with_filters": {
        "get_rows": "works",
        "filter_rows": [{"column_id": "publication_year", "value": 2024,
                         "operator": ">="}],
        "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}],
    },
    "select_only": {"get_rows": "works",
                    "select": ["id", "display_name", "cited_by_count"]},
    "seeded_sample": {"get_rows": "works", "sample": 100, "seed": "42"},
    "seed_int": {"get_rows": "works", "sample": 10, "seed": 7},
    "per_page_page": {"get_rows": "works", "per_page": 50, "page": 2},
    "cursor": {"get_rows": "works", "cursor": "*"},
    "everything": {
        "get_rows": "works",
        "filter_rows": [{"column_id": "type", "value": "article"}],
        "sort_by": [
            {"column_id": "publication_year", "direction": "desc"},
            {"column_id": "cited_by_count", "direction": "desc"},
        ],
        "sample": 50, "seed": "x9",
        "select": ["id", "display_name"],
        "per_page": 25, "page": 3,
    },
}


@pytest.mark.parametrize("name", sorted(ROUND_TRIP_DICTS))
def test_dict_round_trip_lossless(name):
    """`to_dict(from_dict(x)) == x` — no logistics field is dropped or invented."""
    src = ROUND_TRIP_DICTS[name]
    assert OQO.from_dict(src).to_dict() == src


def test_absent_logistics_fields_not_emitted():
    """A minimal OQO emits NO logistics keys (canonical OQOs stay minimal)."""
    out = OQO.from_dict({"get_rows": "works"}).to_dict()
    for key in ("select", "seed", "per_page", "page", "cursor"):
        assert key not in out


def test_empty_select_not_emitted():
    """An explicitly-empty select round-trips to absent (≡ full object)."""
    out = OQO.from_dict({"get_rows": "works", "select": []}).to_dict()
    assert "select" not in out


# --- URL → OQO parsing -------------------------------------------------------

def test_parse_select_into_oqo():
    oqo = parse_url_to_oqo("works", select_string="id,display_name,cited_by_count")
    assert oqo.select == ["id", "display_name", "cited_by_count"]


def test_parse_select_preserves_order_and_strips_ws():
    oqo = parse_url_to_oqo("works", select_string=" b , a ,c")
    assert oqo.select == ["b", "a", "c"]


def test_parse_full_logistics_url():
    """The worked example from EXPLORE.md parses every field onto the OQO."""
    oqo = parse_url_to_oqo(
        "works",
        select_string="id,display_name",
        per_page=50, page=2, sample=10, seed="7",
    )
    assert oqo.select == ["id", "display_name"]
    assert oqo.per_page == 50
    assert oqo.page == 2
    assert oqo.sample == 10
    assert oqo.seed == "7"


def test_parse_cursor():
    oqo = parse_url_to_oqo("works", cursor="*")
    assert oqo.cursor == "*"
    assert oqo.page is None


# --- OQO → URL rendering reproduces the params -------------------------------

def test_render_round_trips_select_and_pagination():
    oqo = OQO.from_dict({
        "get_rows": "works",
        "select": ["id", "display_name", "cited_by_count"],
        "per_page": 50, "page": 2, "sample": 10, "seed": "7",
    })
    rendered = render_oqo_to_url(oqo)
    assert rendered["select"] == "id,display_name,cited_by_count"
    assert rendered["per_page"] == 50
    assert rendered["page"] == 2
    assert rendered["sample"] == 10
    assert rendered["seed"] == "7"


def test_render_omits_absent_logistics():
    rendered = render_oqo_to_url(OQO.from_dict({"get_rows": "works"}))
    assert rendered["select"] is None
    assert rendered["seed"] is None
    assert rendered["per_page"] is None
    assert rendered["page"] is None
    assert rendered["cursor"] is None


# --- Canonicalizer passes logistics through ----------------------------------

def test_canonicalizer_preserves_logistics():
    oqo = OQO.from_dict({
        "get_rows": "works",
        "select": ["id", "display_name"],
        "sample": 50, "seed": "42", "per_page": 25, "page": 2,
    })
    canon = canonicalize_oqo(oqo)
    assert canon.select == ["id", "display_name"]
    assert canon.seed == "42"
    assert canon.per_page == 25
    assert canon.page == 2
    assert canon.sample == 50


def test_canonicalizer_does_not_inject_pagination_defaults():
    """Absent pagination stays absent in canonical form (open-decision #2)."""
    canon = canonicalize_oqo(OQO.from_dict({"get_rows": "works"}))
    out = canon.to_dict()
    assert "per_page" not in out
    assert "page" not in out
