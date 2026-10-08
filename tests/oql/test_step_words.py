"""The echo's step words (oxjob #1555, Jason 2026-10-05): a comma after the
opener; one step `then`, two `then` + `finally`, three or more `first`, `then`
..., `finally` (no `first`, 2026-10-08); the last step `summarize using`. Input takes any opener anywhere,
with or without the comma, and `calculate` / `summarize with` / `summarize by`."""
import os

import pytest
import yaml

from query_translation.oql_lang import parse, render
from query_translation.oql_pipeline import render_pipeline_line, transitions
from query_translation.oqo_canonicalizer import canonicalize_oqo
from tests.oql._echo import launch_form

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "oql", "corpus.yaml")


def _canon(q):
    return canonicalize_oqo(parse(q))


def _line(q):
    return render_pipeline_line(_canon(q))


def test_transitions():
    assert transitions(0) == []
    assert transitions(1) == ["then"]
    assert transitions(2) == ["then", "finally"]
    assert transitions(3) == ["then", "then", "finally"]
    assert transitions(4) == ["then", "then", "then", "finally"]


@pytest.mark.parametrize("q", [
    "get works where year > 2020; then, sample 100 of those works",
    "get works where year > 2020; then, group those works by year; "
    "finally, summarize using count",
    "get works where year > 2020; then, group those works by year and type; "
    "finally, summarize using count and mean FWCI",
    "get works where year >= 2020; then, get each funder of those works; "
    "then, get all that funder's works; then, group those works by year; "
    "finally, summarize using mean citation count",
])
def test_echo_is_its_own_canonical_form(q):
    assert _line(q) == q


@pytest.mark.parametrize("typed", [
    "get works where year > 2020; then group those works by year; then calculate count",
    "get works where year > 2020; then group by year; finally summarize count",
    "get works where year > 2020; first group by year; next, summarize with count",
    "get works where year > 2020; then, group by year; lastly, summarize by count",
    "get works where year > 2020 then group by year then calculate count",
    "get works where year > 2020; finally, group by year; first, calculate count",
])
def test_any_opener_any_order(typed):
    assert _line(typed) == ("get works where year > 2020; then, group those works by "
                            "year; finally, summarize using count")


def test_multi_line_echo_carries_the_step_words():
    q = ("get works where institution is I63966007 and year >= 2015; "
         "then, group those works by author where count of those works > 10 and by year; "
         "finally, summarize using count, mean FWCI, and percent open access")
    lines = render(_canon(q), style="pipeline").split("\n")
    assert [ln.split(",")[0] for ln in lines[1:]] == ["then", "finally"]
    assert all(ln.endswith(";") for ln in lines[:-1])


def _pipeline_rows():
    rows = yaml.safe_load(open(CORPUS))["rows"]
    return [r for r in rows if r.get("status") == "ok" and r.get("oqo")
            and "pipeline" in (r.get("tags") or [])]


@pytest.mark.parametrize("row", _pipeline_rows(), ids=lambda r: str(r["id"]))
def test_launch_form_still_parses_the_same(row):
    flat = " ".join(row["oql"].replace(";\n", "; ").split())
    flat = flat.replace("( ", "(").replace(" )", ")")
    old = launch_form(flat)
    assert _canon(old).to_dict() == _canon(flat).to_dict()
