"""Pipeline results as flat CSV downloads (oxjob #1550): the groups as one CSV (one row
per innermost group, a column per split); the summary as all-works.csv plus, with two or
more splits, by-<split>.csv for each split on its own: one plain CSV when that is all,
else a zip. Exports have bitten us before (Jason, 2026-10-08), so the edge cases are
pinned here: missing values, quoting, repeated split names, a group's own field, shares,
responses without meta.splits or a summary, and the file names."""
import csv
import io
import zipfile

import pytest

from query_translation import analytics_csv
from query_translation.oql_lang import parse
from query_translation.oqo_canonicalizer import canonicalize_oqo

Q = ("get works where year >= (2020); then group those works by institution in "
     "(I1, I2); then group those works again by year; then calculate count, mean FWCI")
COUNT = {"key": "count", "measure": "count", "oql": "count"}
FWCI = {"key": "mean_fwci", "measure": "mean", "oql": "mean FWCI"}
SHARE = {"key": "percent_of_those", "measure": "percent_of_those", "oql": "percent of those works"}
HINDEX = {"key": "value_summary_stats_h_index", "measure": "value", "oql": "h-index"}


def _oqo(q=Q):
    return canonicalize_oqo(parse(q))


def _row(key, name, count, fwci, groups=None, **extra):
    r = {"key": key, "key_display_name": name, "count": count, "mean_fwci": fwci, **extra}
    if groups is not None:
        r["groups"] = groups
    return r


def _body(oqo=None):
    oqo = oqo or _oqo()
    years = lambda a, b: [_row("2020", "2020", a, 1.5), _row("2021", "2021", b, None)]  # noqa: E731
    mit = _row("https://openalex.org/I1", "MIT", 10, 2.0)
    stanford = _row("https://openalex.org/I2", "Stanford", 8, 1.75)
    return {
        "meta": {"count": 100, "measures": [COUNT, FWCI],
                 "splits": [analytics_csv.split_meta(g, "works") for g in oqo.group_by]},
        "summary": {"all": _row("all", "all works", 100, 1.0),
                    "splits": [{"groups": [mit, stanford], "more_groups": False},
                               {"groups": years(60, 40), "more_groups": False}]},
        "group_by": [dict(mit, groups=years(6, 4)), dict(stanford, groups=years(5, 3))],
    }


def _read(text):
    return list(csv.reader(io.StringIO(text)))


def _zip(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: _read(z.read(n).decode("utf-8")) for n in z.namelist()}


# --- the groups --------------------------------------------------------------------

def test_the_groups_are_one_flat_csv_a_column_per_split():
    data, name, mime, rows = analytics_csv.build_download(_body(), _oqo(), Q)
    assert mime == "text/csv"
    assert name.startswith("openalex-get-works-where-year-2020") and name.endswith(".csv")
    assert "-summary" not in name
    rows = _read(data.decode("utf-8"))
    assert rows[0] == ["institution", "institution id", "year", "count", "mean FWCI"]
    assert rows[1] == ["MIT", "I1", "2020", "6", "1.5"]
    assert rows[2] == ["MIT", "I1", "2021", "4", ""]          # a missing value is empty
    assert rows[3] == ["Stanford", "I2", "2020", "5", "1.5"]  # every row names its groups
    assert len(rows) == 5


def test_no_split_is_one_row_the_whole_set_without_shares():
    oqo = _oqo("get works where year >= (2020); then calculate count, mean FWCI")
    body = {"meta": {"measures": [COUNT, FWCI, SHARE], "splits": []},
            "summary": {"all": {"key": "all", "key_display_name": "all works", "count": 7,
                                "mean_fwci": 1.25}},
            "group_by": []}
    data, name, mime, rows = analytics_csv.build_download(body, oqo, "q")
    assert _read(data.decode()) == [["count", "mean FWCI"], ["7", "1.25"]]
    data, name, mime, rows = analytics_csv.build_download(body, oqo, "q", "summary")
    assert mime == "text/csv" and name == "openalex-q-summary.csv"
    assert _read(data.decode()) == [["count", "mean FWCI"], ["7", "1.25"]]


def test_an_empty_result_is_a_header_only():
    body = _body()
    body["group_by"] = []
    rows = _read(analytics_csv.groups_csv(body, _oqo()))
    assert rows == [["institution", "institution id", "year", "count", "mean FWCI"]]


def test_an_outer_group_with_no_inner_groups_has_no_row():
    body = _body()
    body["group_by"].append(_row("https://openalex.org/I3", "Harvard", 0, None, groups=[]))
    assert len(_read(analytics_csv.groups_csv(body, _oqo()))) == 5


def test_commas_quotes_newlines_and_unicode_survive():
    body = _body()
    body["group_by"][0]["key_display_name"] = 'Université "Paris", Saclay\nCampus'
    rows = _read(analytics_csv.groups_csv(body, _oqo()))
    assert rows[1][0] == 'Université "Paris", Saclay\nCampus'
    assert len(rows) == 5


def test_a_missing_name_falls_back_to_the_key():
    body = _body()
    body["group_by"][1]["key_display_name"] = None
    assert _read(analytics_csv.groups_csv(body, _oqo()))[3][:2] == ["https://openalex.org/I2", "I2"]


def test_without_meta_splits_the_columns_come_from_the_query():
    body = _body()
    body["meta"].pop("splits")
    assert _read(analytics_csv.groups_csv(body, _oqo()))[0][:3] == ["institution", "institution id", "year"]


def test_repeated_split_names_get_a_number():
    q = ("get works where year >= (2020); then group those works into ((year <= (2021)), "
         "(year >= (2022))); then group those works again into ((type is (article)), "
         "(type is (review))); then calculate count")
    oqo = _oqo(q)
    cond = lambda k, n, groups=None: _row(k, k, n, None, groups)  # noqa: E731
    body = {"meta": {"measures": [COUNT], "splits": [analytics_csv.split_meta(g, "works") for g in oqo.group_by]},
            "summary": {"all": _row("all", "all works", 9, None),
                        "splits": [{"groups": [cond("a", 4), cond("b", 5)]},
                                   {"groups": [cond("c", 6), cond("d", 3)]}]},
            "group_by": [cond("a", 4, [cond("c", 3)]), cond("b", 5, [cond("d", 2)])]}
    assert _read(analytics_csv.groups_csv(body, oqo))[0] == ["condition", "condition 2", "count"]
    data, name, mime, rows = analytics_csv.build_download(body, oqo, q, "summary")
    files = _zip(data)
    assert sorted(files) == ["all-works.csv", "by-condition-2.csv", "by-condition.csv"]
    assert files["by-condition-2.csv"] == [["condition", "count"], ["c", "6"], ["d", "3"]]


# --- the summary -------------------------------------------------------------------

def test_two_splits_summary_is_a_zip_all_works_and_each_split_alone():
    data, name, mime, rows = analytics_csv.build_download(_body(), _oqo(), Q, "summary")
    assert mime == "application/zip" and name.endswith("-summary.zip")
    files = _zip(data)
    assert list(files) == ["all-works.csv", "by-institution.csv", "by-year.csv"]
    assert files["all-works.csv"] == [["count", "mean FWCI"], ["100", "1"]]
    assert files["by-institution.csv"] == [["institution", "institution id", "count", "mean FWCI"],
                                           ["MIT", "I1", "10", "2"], ["Stanford", "I2", "8", "1.75"]]
    assert files["by-year.csv"] == [["year", "count", "mean FWCI"], ["2020", "60", "1.5"],
                                    ["2021", "40", ""]]


def test_one_split_summary_is_one_plain_csv():
    oqo = _oqo("get works where year >= (2020); then group those works by year; then calculate count, mean FWCI")
    body = _body(oqo)
    body["summary"].pop("splits")
    data, name, mime, rows = analytics_csv.build_download(body, oqo, "q", "summary")
    assert mime == "text/csv" and name == "openalex-q-summary.csv"
    assert _read(data.decode()) == [["count", "mean FWCI"], ["100", "1"]]


def test_shares_and_own_fields_only_where_they_mean_something():
    oqo = _oqo("get works where year >= (2020); then group those works by author; then group "
               "those works again by year; then calculate count, percent of those works, h-index")
    splits = [analytics_csv.split_meta(g, "works") for g in oqo.group_by]
    a1 = {"key": "https://openalex.org/A1", "key_display_name": "Ana", "count": 5,
          "percent_of_those": 50.0, HINDEX["key"]: 12}
    y = {"key": "2020", "key_display_name": "2020", "count": 10, "percent_of_those": 100.0}
    body = {"meta": {"measures": [COUNT, SHARE, HINDEX], "splits": splits},
            "summary": {"all": {"key": "all", "key_display_name": "all works", "count": 10},
                        "splits": [{"groups": [a1]}, {"groups": [y]}]},
            "group_by": [dict(a1, groups=[y])]}
    files = _zip(analytics_csv.build_download(body, oqo, "q", "summary")[0])
    assert files["all-works.csv"] == [["count"], ["10"]]          # no share, no h-index
    assert files["by-author.csv"][0] == ["author", "author id", "count", "percent of those works", "h-index"]
    assert files["by-author.csv"][1] == ["Ana", "A1", "5", "50", "12"]
    assert files["by-year.csv"][0] == ["year", "count", "percent of those works"]  # years have no h-index


def test_a_response_without_a_summary_still_downloads():
    body = _body()
    body.pop("summary")
    files = _zip(analytics_csv.build_download(body, _oqo(), Q, "summary")[0])
    assert files["all-works.csv"] == [["count", "mean FWCI"], ["", ""]]
    assert files["by-year.csv"] == [["year", "count", "mean FWCI"]]


# --- names -------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("get works where year >= (2020)", "openalex-get-works-where-year-2020.csv"),
    ("", "openalex-query.csv"),
    ("工程", "openalex-query.csv"),                       # nothing ASCII left
    ("get   works\n  where", "openalex-get-works-where.csv"),
])
def test_file_names_are_safe_ascii(text, expected):
    assert analytics_csv.filename(text) == expected


def test_long_queries_cut_the_name_at_80_characters():
    name = analytics_csv.filename("get works where " + "title-abstract has (kelp) and " * 10)
    assert len(name) <= len("openalex-") + 80 + len(".csv") and not name.endswith("-.csv")


def test_split_meta_names_each_split_in_oql_words():
    oqo = _oqo(
        "get works where year >= (2020); then group those works into citation count bins "
        "of (10); then group those works again by title-abstract search in ((kelp))")
    got = [analytics_csv.split_meta(g, "works") for g in oqo.group_by]
    assert [(s["oql"], s["kind"], s["has_ids"]) for s in got] == [
        ("citation count bins", "bins", False), ("title-abstract search", "searches", False)]


# --- price and rows (Jason, 2026-10-08: the query's price for every 100 rows) -------

def test_rows_count_data_rows_even_with_line_breaks_in_values():
    body = _body()
    body["group_by"][0]["key_display_name"] = "two\nlines"
    data, name, mime, rows = analytics_csv.build_download(body, _oqo(), Q)
    assert rows == 4
    data, name, mime, rows = analytics_csv.build_download(_body(), _oqo(), Q, "summary")
    assert rows == 1 + 2 + 2          # all works, two institutions, two years


@pytest.mark.parametrize("rows,units", [(0, 1), (1, 1), (100, 1), (101, 2), (10_000, 100), (128_284, 1283)])
def test_an_export_costs_the_query_price_per_100_rows(rows, units):
    from query_translation.analytics import export_price
    for base in (1, 10, 31):
        p = export_price({"credits": base, "usd": base * 0.0001, "steps": []}, rows)
        assert p["credits"] == base * units
        assert p["usd"] == round(base * units * 0.0001, 6)
        assert sum(s["credits"] for s in p["steps"]) == p["credits"] - base   # the extra over the base
