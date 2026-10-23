"""How a table of groups is ordered (oxjob #1555, D4): years oldest first by default, a
sort ES can't do (a percent, a group's own field) covers every group of a single split,
and two splits honor the order at every level. The engine runs against a fake `_search`
here; the live checks are in the job (work/scripts/groups_probe.py)."""
import pytest

from query_translation import analytics as A
from query_translation.oql_parser import parse_either


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_order_value_reads_number_like_keys_as_numbers():
    assert A._order_value("999") < A._order_value("2026")
    assert A._order_value(3) < A._order_value("US")      # numbers before text, no TypeError
    assert A._order_value("b") > A._order_value("A")       # text ignores case


def test_sort_rows_keeps_incoming_order_for_ties_and_puts_missing_last():
    rows = [{"key": "a", "count": 9, "p": 100.0}, {"key": "b", "count": 5, "p": None},
            {"key": "c", "count": 4, "p": 100.0}, {"key": "d", "count": 2, "p": 50.0}]
    out = A._sort_rows(rows, ("p", "desc"))
    assert [r["key"] for r in out] == ["a", "c", "d", "b"]   # ties: most works first
    out = A._sort_rows(rows, ("p", "asc"))
    assert [r["key"] for r in out] == ["d", "a", "c", "b"]


def _lv(i, column_id, kind="terms"):
    return A.Level(i, None, kind, column_id=column_id)


def test_year_levels_default_to_oldest_first():
    year, country = _lv(0, "publication_year"), _lv(1, "authorships.countries")
    rows = [{"key": "2026", "count": 9}, {"key": "1999", "count": 1}, {"key": "2010", "count": 3}]
    assert [r["key"] for r in A._default_order(year, rows)] == ["1999", "2010", "2026"]
    assert A._default_order(country, rows) is rows           # ES order (most works first)
    assert not A._is_year_level(_lv(0, "publication_year", kind="histogram"))


def _nested_rows():
    return [
        {"key": "2025", "count": 10, "m": 1.0, "groups": [
            {"key": "US", "count": 6, "m": 0.5}, {"key": "CN", "count": 4, "m": 2.0}]},
        {"key": "2023", "count": 30, "m": 3.0, "groups": [
            {"key": "CN", "count": 20, "m": 1.0}, {"key": "US", "count": 10, "m": 4.0}]},
    ]


def test_two_splits_default_order_each_level():
    levels = [_lv(0, "publication_year"), _lv(1, "authorships.countries")]
    out = A._order_levels(levels, _nested_rows(), None)
    assert [r["key"] for r in out] == ["2023", "2025"]                 # years oldest first
    assert [g["key"] for g in out[0]["groups"]] == ["CN", "US"]        # as ES gave them


def test_two_splits_key_sort_orders_the_outer_split_only():
    levels = [_lv(0, "publication_year"), _lv(1, "authorships.countries")]
    out = A._order_levels(levels, _nested_rows(), ("key", "desc"))
    assert [r["key"] for r in out] == ["2025", "2023"]
    assert [g["key"] for g in out[1]["groups"]] == ["CN", "US"]


def test_two_splits_number_sort_orders_every_level():
    levels = [_lv(0, "publication_year"), _lv(1, "authorships.countries")]
    out = A._order_levels(levels, _nested_rows(), ("m", "desc"))
    assert [r["key"] for r in out] == ["2023", "2025"]
    assert [g["key"] for g in out[0]["groups"]] == ["US", "CN"]
    assert [g["key"] for g in out[1]["groups"]] == ["CN", "US"]


# ---------------------------------------------------------------------------
# run() against a fake ES
# ---------------------------------------------------------------------------
class FakeES:
    """Answers the engine's requests: `cards` for the cardinality probe, `buckets` (a
    list of (key, doc_count, {sub-agg name: value})) for the main split request."""

    def __init__(self, buckets, cards=None, other=0, total=None):
        self.buckets, self.cards, self.other = buckets, cards or {}, other
        self.total = total if total is not None else sum(b[1] for b in buckets)
        self.bodies = []

    def search(self, index, connection, body, deadline, what, **params):
        self.bodies.append(body)
        aggs = body.get("aggs") or {}
        out = {}
        for name in aggs:
            if name.startswith("card"):
                out[name] = {"value": self.cards.get(name, len(self.buckets))}
        if "s0" in aggs:
            t = aggs["s0"]["terms"]
            order = t.get("order") or [{"_count": "desc"}]
            bs = list(self.buckets)
            if order[0] == {"_key": "asc"}:
                bs.sort(key=lambda b: A._order_value(b[0]))
            elif order[0] == {"_key": "desc"}:
                bs.sort(key=lambda b: A._order_value(b[0]), reverse=True)
            else:
                bs.sort(key=lambda b: -b[1])
            size = t.get("size", 10)
            kept = bs[:size]
            rows = []
            for k, n, sub in kept:
                b = {"key": k, "doc_count": n}
                for sname, v in (sub or {}).items():
                    b[sname] = v
                rows.append(b)
            out["s0"] = {"buckets": rows,
                         "sum_other_doc_count": self.other + sum(b[1] for b in bs[size:])}
        if "n_groups" in aggs:
            out["n_groups"] = {"value": len(self.buckets)}
        for name, a in aggs.items():
            if name.startswith("m_") and "filter" in a:
                out[name] = {"doc_count": 0}
        return {"hits": {"total": {"value": self.total}}, "took": 1, "aggregations": out}


def _run(monkeypatch, oql, fake, **kw):
    from works.fields import fields_dict
    monkeypatch.setattr(A, "_search", fake.search)
    monkeypatch.setattr(A, "name_rows", lambda levels, rows, connection: rows)
    oqo = parse_either(oql)
    sort = (oqo.sort_by[0].column_id, oqo.sort_by[0].direction) if oqo.sort_by else None
    sort = kw.pop("sort", sort)
    return A.run(oqo, index_name="works", connection=None, fields_dict=fields_dict,
                 base_query={"match_all": {}}, sort=sort, **kw)


def test_a_year_split_reads_oldest_first_with_no_sort(monkeypatch):
    fake = FakeES([("2026", 50, {}), ("1990", 1, {}), ("2001", 7, {})])
    body = _run(monkeypatch, "get the count and share of works about kelp by year", fake, per_page=2)
    assert fake.bodies[-1]["aggs"]["s0"]["terms"]["order"][0] == {"_key": "asc"}
    assert [r["key"] for r in body["group_by"]] == ["1990", "2001"]


def test_a_year_split_still_sorts_when_asked(monkeypatch):
    fake = FakeES([("2026", 50, {}), ("1990", 1, {}), ("2001", 7, {})])
    body = _run(monkeypatch, "get the count and share of works about kelp by year", fake, per_page=2,
                sort=("count", "desc"))
    assert [r["key"] for r in body["group_by"]] == ["2026", "2001"]


def test_a_percent_sort_reads_every_group(monkeypatch):
    # three countries; the smallest has the highest rate, so a page of 1 by count would
    # have missed it
    fake = FakeES([("US", 100, {"m_percent_open_access_is_oa": {"doc_count": 40}}),
                   ("CN", 50, {"m_percent_open_access_is_oa": {"doc_count": 30}}),
                   ("NU", 2, {"m_percent_open_access_is_oa": {"doc_count": 2}})])
    body = _run(monkeypatch, "get the percent open access of all works by country, highest first", fake,
                per_page=1)
    main = fake.bodies[-1]["aggs"]["s0"]["terms"]
    assert main["size"] >= 3                       # sized to every group, not the page
    assert body["group_by"][0]["percent_open_access_is_oa"] == 100.0
    assert body["meta"]["groups_count"] == 3 and body["meta"]["more_groups"] is True


def test_a_percent_sort_over_too_many_groups_is_refused_loudly(monkeypatch):
    fake = FakeES([("I1", 5, {})], cards={"card0": A.ALL_GROUPS_SORT_LIMIT + 1})
    with pytest.raises(A.AnalyticsError) as ei:
        _run(monkeypatch, "get the percent open access of all works by institution, highest first", fake)
    assert ei.value.code == "too_many_groups" and ei.value.fix
    assert "percent open access" in ei.value.message


def test_an_all_groups_read_that_comes_back_short_is_refused(monkeypatch):
    fake = FakeES([("US", 100, {}), ("CN", 50, {})], cards={"card0": 2}, other=7)
    with pytest.raises(A.AnalyticsError) as ei:
        _run(monkeypatch, "get the percent open access of all works by country, highest first", fake)
    assert ei.value.code == "too_many_groups"


def test_a_share_sort_orders_like_the_count_in_es(monkeypatch):
    fake = FakeES([("US", 100, {}), ("CN", 50, {})])
    _run(monkeypatch, "get the count and share of works about kelp by country", fake,
         sort=("percent_of_those", "desc"))
    assert fake.bodies[-1]["aggs"]["s0"]["terms"]["order"][0] == {"_count": "desc"}


def test_an_own_field_sort_reads_every_group_once(monkeypatch):
    h = {"https://openalex.org/A1": 10, "https://openalex.org/A2": 85,
         "https://openalex.org/A3": 63}
    calls = []

    def fake_fill(levels, rows, measures, deadline, start_level=0):
        calls.append(len(rows))
        for r in rows:
            r["summary_stats_h_index"] = h.get(r["key"])
    monkeypatch.setattr(A, "fill_own_values", fake_fill)
    fake = FakeES([("https://openalex.org/A1", 90, {}), ("https://openalex.org/A3", 82, {}),
                   ("https://openalex.org/A2", 50, {})])
    body = _run(monkeypatch, "get the count of works about kelp by author. Show h-index.", fake,
                per_page=2, sort=("summary_stats_h_index", "desc"))
    assert [r["key"] for r in body["group_by"]] == ["https://openalex.org/A2",
                                                    "https://openalex.org/A3"]
    assert calls == [3]          # every group looked up once, not again for the page


# ---------------------------------------------------------------------------
# Codes sorted by name (#1658): `alphabetical by country` sorted country codes, so
# United Arab Emirates came before Albania and the reverse started with South Africa
# ---------------------------------------------------------------------------
def _coded(codes, level_i=0):
    return [{"key": f"https://openalex.org/countries/{c}", "count": 1, "_raw": (level_i, c)}
            for c in codes]


def _named_lv(i, column_id):
    return A.Level(i, None, "terms", column_id=column_id,
                   name_vocab=A._name_vocab(column_id, "works"))


def test_only_codes_whose_order_reads_alphabetical_sort_by_name():
    assert A._name_vocab("authorships.countries", "works")
    assert A._name_vocab("language", "works")
    assert A._name_vocab("publication_year", "works") is None              # years
    assert A._name_vocab("authorships.institutions.id", "works") is None   # ID order


def test_a_key_sort_on_countries_goes_by_the_shown_name_with_unknown_last():
    lv = _named_lv(0, "authorships.countries")
    rows = _coded(["AE", "unknown", "ZA", "AL", "US"])
    codes = lambda rs: [r["_raw"][1] for r in rs]   # noqa: E731
    assert codes(A._sort_rows(rows, ("key", "asc"), lv)) == ["AL", "ZA", "AE", "US", "unknown"]
    assert codes(A._sort_rows(rows, ("key", "desc"), lv)) == ["US", "AE", "ZA", "AL", "unknown"]
    # a level with no names (or no level): key order as before
    assert codes(A._sort_rows(rows, ("key", "asc")))[0] == "AE"


def test_languages_sort_by_the_name_the_row_shows():
    lv = _named_lv(0, "language")
    rows = [{"key": k, "count": 1, "_raw": (0, k)} for k in ["zh-cn", "de", "ar"]]
    assert [r["key"] for r in A._sort_rows(rows, ("key", "asc"), lv)] == ["ar", "zh-cn", "de"]
    # Arabic, Chinese (zh-cn, shown as "Chinese"), German


_COUNTRIES = [("AE", 4, {}), ("AL", 1, {}), ("AR", 207, {}), ("ZA", 437, {}), ("ZM", 3, {})]


def test_alphabetical_by_country_reads_every_group_and_sorts_by_name(monkeypatch):
    fake = FakeES(list(_COUNTRIES))
    body = _run(monkeypatch, "get the count of works about kelp by country, alphabetical by country",
                fake, per_page=2)
    assert len(fake.bodies) == 1                             # no cardinality probe first
    main = fake.bodies[-1]["aggs"]["s0"]["terms"]
    assert main["size"] >= 247                               # every country, not a page of codes
    assert [r["key"][-2:] for r in body["group_by"]] == ["AL", "AR"]   # Albania, Argentina
    assert body["meta"]["groups_count"] == 5 and body["meta"]["more_groups"] is True


def test_reverse_alphabetical_by_country_starts_with_z(monkeypatch):
    fake = FakeES(list(_COUNTRIES))
    body = _run(monkeypatch, "get the count of works about kelp by country, reverse alphabetical by country",
                fake, per_page=2)
    assert [r["key"][-2:] for r in body["group_by"]] == ["ZM", "AE"]   # Zambia, United Arab Emirates


def test_two_splits_key_sort_orders_countries_by_name():
    levels = [_named_lv(0, "authorships.countries"), _lv(1, "publication_year")]
    rows = _coded(["AE", "AL"])
    rows[0]["groups"] = [{"key": "2025", "count": 1}, {"key": "2023", "count": 1}]
    out = A._order_levels(levels, rows, ("key", "asc"))
    assert [r["_raw"][1] for r in out] == ["AL", "AE"]
    assert [g["key"] for g in out[1]["groups"]] == ["2023", "2025"]   # inner: years oldest first
