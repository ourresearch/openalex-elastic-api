"""The website's sort menu reads its choices from the API (oxjob #1658): every choice
is an order the editor offers, read back by the parser, so it carries the exact
`sort_by` it sets, and setting that `sort_by` makes the sentence end with its words."""
from dataclasses import replace

import pytest

from query_translation import oql_core as C
from query_translation.oqo import SortBy
from query_translation.oql_orders import describe_order, orders_for
from query_translation.oql_parser import parse_either

UBC = "[University of British Columbia](I141945490)"

SHAPES = [
    "get works about kelp",
    "get works about kelp, newest first",
    f"get works from {UBC} since 2024",
    f"get authors at {UBC}",
    "get the count and mean FWCI of works about kelp by country",
    "get the count of works about kelp by country. Show works count.",
    "get the count of works about kelp by author. Show h-index. Only authors with at least 5 works about kelp.",
    "get the count of works about kelp by year",
    "get the count of works about kelp by year and country",
    "get the mean FWCI of works about kelp by institution",
]


def _words(r):
    return [o["words"] for o in r["options"]]


def _option(r, words):
    return next(o for o in r["options"] if o["words"] == words)


@pytest.mark.parametrize("oql", SHAPES)
def test_every_option_sets_an_order_that_reads_as_its_words(oql):
    r = orders_for(oql)
    assert r["options"][0].get("default") and r["options"][0]["sort_by"] == []
    base = parse_either(oql)
    for o in r["options"]:
        oqo = replace(base, sort_by=[SortBy.from_dict(s) for s in o["sort_by"]])
        words, is_default = describe_order(oqo)
        assert words == o["words"], (oql, o)
        assert is_default == bool(o.get("default"))
        text = C.render_core(oqo)
        if o.get("default"):
            assert not any(text.split(". ")[0].endswith(", " + x["words"]) for x in r["options"])
        else:
            assert text.split(". Show ")[0].split(". Only ")[0].endswith(", " + o["words"])


@pytest.mark.parametrize("oql", SHAPES)
def test_one_entry_per_order(oql):
    r = orders_for(oql)
    assert len(_words(r)) == len(set(_words(r)))
    sorts = [tuple((s["column_id"], s["direction"]) for s in o["sort_by"]) for o in r["options"]]
    assert len(sorts) == len(set(sorts))


def test_a_search_defaults_to_best_matches_and_offers_age_adjusted():
    r = orders_for("get works about kelp")
    assert (r["order"], r["order_default"]) == ("best matches first", True)
    assert _option(r, "most cited first")["sort_by"] == [{"column_id": "cited_by_count", "direction": "desc"}]
    assert C.AGE_ADJUSTED_WORDS in _words(r)


def test_works_without_a_search_default_to_age_adjusted_once():
    r = orders_for(f"get works from {UBC} since 2024")
    assert (r["order"], r["order_default"]) == (C.AGE_ADJUSTED_WORDS, True)
    assert _words(r).count(C.AGE_ADJUSTED_WORDS) == 1 and _words(r)[0] == C.AGE_ADJUSTED_WORDS
    assert "best matches first" not in _words(r)


def test_a_typed_order_is_the_current_one():
    r = orders_for("get works about kelp, newest first")
    assert (r["order"], r["order_default"]) == ("newest first", False)
    r = orders_for("get works about kelp, highest reference count first")   # not in the menu
    assert (r["order"], r["order_default"]) == ("highest reference count first", False)


def test_things_default_to_most_works_and_offer_their_own_fields():
    r = orders_for(f"get authors at {UBC}")
    assert _words(r)[0] == "most works first"
    assert "highest works count first" not in _words(r)        # the default, under another name
    assert "highest h-index first" in _words(r)


def test_a_table_offers_names_but_never_adds_a_column():
    r = orders_for("get the count and mean FWCI of works about kelp by country")
    assert "alphabetical by country" in _words(r)
    assert "highest mean FWCI first" in _words(r)
    assert not any("works count" in w or "h-index" in w for w in _words(r))   # not shown
    shown = orders_for("get the count of works about kelp by country. Show works count.")
    assert "highest works count first" in _words(shown)        # shown, so offered


def test_years_default_to_oldest_first():
    r = orders_for("get the count of works about kelp by year")
    assert (r["order"], r["order_default"]) == ("oldest first", True)
    assert _option(r, "newest first")["sort_by"] == [{"column_id": "key", "direction": "desc"}]
    assert _option(r, "most works first")["sort_by"] == [{"column_id": "count", "direction": "desc"}]


def test_id_orders_stay_out_of_the_menu():
    r = orders_for("get the count of works about kelp by institution")
    assert not any(w.endswith("ID order") for w in _words(r))
    assert "fewest works first" in _words(r)


def test_one_number_has_no_order():
    r = orders_for("get the count of works about kelp")
    assert r == {"order": None, "order_default": False, "options": []}


def test_oql_that_does_not_parse_raises():
    with pytest.raises(Exception):
        orders_for("get works wherever")
