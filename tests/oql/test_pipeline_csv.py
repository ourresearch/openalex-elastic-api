"""Pipeline results as a zip (oxjob #1530; spec from #1536): groups.csv one row per
innermost group, totals.csv the total and subtotal rows, query.oql the query."""
import csv
import io
import zipfile

from query_translation import analytics_csv
from query_translation.oql_lang import parse
from query_translation.oqo_canonicalizer import canonicalize_oqo

Q = ("get works where year >= (2020); then group those works by institution in "
     "(I1, I2); then group those works again by year; then calculate count, mean FWCI")


def _body():
    def row(key, name, count, fwci, groups=None):
        r = {"key": key, "key_display_name": name, "count": count, "mean_fwci": fwci}
        if groups is not None:
            r["groups"] = groups
        return r
    years = lambda a, b: [row("2020", "2020", a, 1.5), row("2021", "2021", b, None)]  # noqa: E731
    return {
        "meta": {"measures": [{"key": "count", "oql": "count"},
                              {"key": "mean_fwci", "oql": "mean FWCI"}]},
        "total": row("total", "all works", 100, 1.0, groups=years(60, 40)),
        "group_by": [row("https://openalex.org/I1", "MIT", 10, 2.0, groups=years(6, 4)),
                     row("https://openalex.org/I2", "Stanford", 8, 1.75, groups=years(5, 3))],
    }


def _read(z, name):
    return list(csv.reader(io.StringIO(z.read(name).decode())))


def test_the_zip_holds_tidy_groups_totals_and_the_query():
    oqo = canonicalize_oqo(parse(Q))
    data, name = analytics_csv.build_zip(oqo, _body(), {"credits": 1, "usd": 0.0001}, Q)
    assert name.startswith("openalex-get-works-where-year-2020") and name.endswith(".zip")
    z = zipfile.ZipFile(io.BytesIO(data))
    groups = _read(z, "groups.csv")
    assert groups[0] == ["institution", "institution id", "year", "count", "mean FWCI"]
    assert groups[1] == ["MIT", "I1", "2020", "6", "1.5"]
    assert groups[2] == ["MIT", "I1", "2021", "4", ""]          # a missing value is empty
    assert len(groups) == 5
    totals = _read(z, "totals.csv")
    assert totals[0][0] == "row"
    assert totals[1] == ["total", "", "", "", "100", "1"]
    assert totals[2] == ["total", "", "", "2020", "60", "1.5"]  # the world by year
    assert ["subtotal", "MIT", "I1", "", "10", "2"] in totals
    query = z.read("query.oql").decode()
    assert query.startswith(Q) and "# price: 1 credit ($0.0001)" in query


def test_split_meta_names_each_split_in_oql_words():
    oqo = canonicalize_oqo(parse(
        "get works where year >= (2020); then group those works into citation count bins "
        "of (10); then group those works again by title-abstract search in ((kelp))"))
    got = [analytics_csv.split_meta(g, "works") for g in oqo.group_by]
    assert [(s["oql"], s["kind"], s["has_ids"]) for s in got] == [
        ("citation count bins", "bins", False), ("title-abstract search", "searches", False)]
