"""Pipeline results as two flat CSVs (oxjob #1550): the groups table, one row per
innermost group with a column per split; the summary table, the whole set and each
split's groups on their own, first column naming what the row summarizes."""
import csv
import io

from query_translation import analytics_csv
from query_translation.oql_lang import parse
from query_translation.oqo_canonicalizer import canonicalize_oqo

Q = ("get works where year >= (2020); then group those works by institution in "
     "(I1, I2); then group those works again by year; then calculate count, mean FWCI")


def _row(key, name, count, fwci, groups=None):
    r = {"key": key, "key_display_name": name, "count": count, "mean_fwci": fwci}
    if groups is not None:
        r["groups"] = groups
    return r


def _body():
    years = lambda a, b: [_row("2020", "2020", a, 1.5), _row("2021", "2021", b, None)]  # noqa: E731
    mit = _row("https://openalex.org/I1", "MIT", 10, 2.0)
    stanford = _row("https://openalex.org/I2", "Stanford", 8, 1.75)
    oqo = canonicalize_oqo(parse(Q))
    return {
        "meta": {"measures": [{"key": "count", "oql": "count"},
                              {"key": "mean_fwci", "oql": "mean FWCI"}],
                 "splits": [analytics_csv.split_meta(g, "works") for g in oqo.group_by]},
        "summary": {"all": _row("all", "all works", 100, 1.0),
                    "splits": [{"groups": [mit, stanford], "more_groups": False},
                               {"groups": years(60, 40), "more_groups": False}]},
        "group_by": [dict(mit, groups=years(6, 4)), dict(stanford, groups=years(5, 3))],
    }


def _read(text):
    return list(csv.reader(io.StringIO(text)))


def test_the_groups_table_is_flat_a_column_per_split():
    text, name = analytics_csv.build_csv(_body(), "works", Q)
    assert name.startswith("openalex-get-works-where-year-2020") and name.endswith(".csv")
    assert not name.endswith("-summary.csv")
    rows = _read(text)
    assert rows[0] == ["institution", "institution id", "year", "count", "mean FWCI"]
    assert rows[1] == ["MIT", "I1", "2020", "6", "1.5"]
    assert rows[2] == ["MIT", "I1", "2021", "4", ""]          # a missing value is empty
    assert rows[3] == ["Stanford", "I2", "2020", "5", "1.5"]  # every row names its groups
    assert len(rows) == 5


def test_the_summary_table_is_the_whole_set_then_each_split_alone():
    text, name = analytics_csv.build_csv(_body(), "works", Q, table="summary")
    assert name.endswith("-summary.csv")
    rows = _read(text)
    assert rows[0] == ["summary of", "institution", "institution id", "year", "count",
                       "mean FWCI"]
    assert rows[1] == ["all works", "", "", "", "100", "1"]
    assert rows[2] == ["institution", "MIT", "I1", "", "10", "2"]
    assert rows[3] == ["institution", "Stanford", "I2", "", "8", "1.75"]
    assert rows[4] == ["year", "", "", "2020", "60", "1.5"]   # the whole set by year
    assert len(rows) == 6


def test_a_calculation_with_no_split_is_one_row_in_both_tables():
    body = {"meta": {"measures": [{"key": "count", "oql": "count"}], "splits": []},
            "summary": {"all": {"key": "all", "key_display_name": "all works", "count": 7}},
            "group_by": []}
    assert _read(analytics_csv.groups_csv(body)) == [["count"], ["7"]]
    assert _read(analytics_csv.summary_csv(body, "works")) == [["summary of", "count"],
                                                                ["all works", "7"]]


def test_one_split_summary_is_the_whole_set_only():
    body = _body()
    body["meta"]["splits"] = body["meta"]["splits"][:1]
    body["summary"].pop("splits")
    body["group_by"] = [dict(r, groups=None) for r in body["group_by"]]
    rows = _read(analytics_csv.summary_csv(body, "works"))
    assert rows[1:] == [["all works", "", "", "100", "1"]]
    assert len(_read(analytics_csv.groups_csv(body))) == 3


def test_split_meta_names_each_split_in_oql_words():
    oqo = canonicalize_oqo(parse(
        "get works where year >= (2020); then group those works into citation count bins "
        "of (10); then group those works again by title-abstract search in ((kelp))"))
    got = [analytics_csv.split_meta(g, "works") for g in oqo.group_by]
    assert [(s["oql"], s["kind"], s["has_ids"]) for s in got] == [
        ("citation count bins", "bins", False), ("title-abstract search", "searches", False)]
