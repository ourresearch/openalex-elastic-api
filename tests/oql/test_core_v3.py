"""OQL core v3 (oxjob #1555): the 44 review cases render and parse back exactly.

Each case in core_v3_cases.json carries the canonical v3 text Jason approved over three
review drafts (2026-10-11) and the OQO it means. Run:
    PYTHONPATH=. pytest tests/oql/test_core_v3.py -q --noconftest
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation.oqo import OQO  # noqa: E402
from query_translation.oql_core import render_core, _and_items  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "core_v3_cases.json")))
NAMES = DATA["names"]
CASES = DATA["cases"]


def resolver(value, column=None):
    return NAMES.get(str(value))


def _id(c):
    return f"{c['case'] or c['label']}-{c['shape']}"


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_renders(c):
    assert render_core(OQO.from_dict(c["oqo"]), resolver) == c["new"]


from query_translation.oql_core import parse_core  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402

COLLECTION_TYPES = {"col_cat": "institutions", "col_peers": "institutions", "col_jmir": "works"}


def _canon(oqo):
    d = canonicalize_oqo(oqo).to_dict()
    d.pop("sort_by", None)
    return d


def _order(oqo):
    """sort_by, with a table's default order (most works first; years oldest first) as none:
    the text never writes it (the cases were written before tables read `get the ...`)."""
    sort = [s.to_dict() for s in oqo.sort_by]
    if oqo.group_by and sort:
        first = oqo.group_by[0].column_id
        if (sort[0]["column_id"], sort[0].get("direction")) == (
                ("key", "asc") if first == "publication_year" else ("count", "desc")):
            return []
    return sort


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_parses_back(c):
    got = parse_core(c["new"], COLLECTION_TYPES.get)
    want = OQO.from_dict(c["oqo"])
    assert _canon(got) == _canon(want)
    assert _order(got) == _order(want)


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_round_trips(c):
    assert render_core(parse_core(c["new"], COLLECTION_TYPES.get), resolver) == c["new"]


# --- the automatic baseline ---------------------------------------------------

from query_translation.oql_core import baseline_oqo  # noqa: E402


def _case(n):
    return next(c for c in CASES if c["case"] == n)


@pytest.mark.parametrize("n", [100, 25, 629, 1073, 621, 1061])
def test_baseline_for_one_named_thing(n):
    oqo = OQO.from_dict(_case(n)["oqo"])
    b = baseline_oqo(oqo)
    assert b is not None
    boqo, star = b
    assert star in oqo.filter_rows and star not in boqo.filter_rows
    assert len(boqo.filter_rows) == len(oqo.filter_rows) - 1
    assert [m.measure for m in boqo.calculate] == ["count", "percent_of_those"]
    assert boqo.group_by == oqo.group_by


@pytest.mark.parametrize("n", [105, 934, 66, 29, 19, 625, 665, 169])
def test_no_baseline(n):
    # nothing named, a rank, a plain list, a number, or no single named thing
    assert baseline_oqo(OQO.from_dict(_case(n)["oqo"])) is None


# --- the shared parse entry -----------------------------------------------------

from query_translation.oql_parser import parse_oql_to_oqo  # noqa: E402


@pytest.mark.parametrize("c", CASES, ids=[_id(c) for c in CASES])
def test_entry_point_reads_core(c):
    got = parse_oql_to_oqo(c["new"])
    if any(x in c["new"] for x in ("col_cat", "col_peers")):
        return   # a collection's type needs users-api
    assert _canon(got) == _canon(OQO.from_dict(c["oqo"]))


@pytest.mark.parametrize("old", [
    "get works where institution is [MIT](I63966007) and published since 2020",
    "get works where title-abstract-keywords has kelp; then, group those works by year; finally, summarize using count",
    "get authors at [University of British Columbia](I141945490) since 2022 who published works where title-abstract-keywords has kelp; then, summarize each author using count",
])
def test_entry_point_keeps_todays_meaning(old):
    from query_translation.oql_lang import parse
    assert canonicalize_oqo(parse_oql_to_oqo(old)).to_dict() == canonicalize_oqo(parse(old)).to_dict()


# --- behaviors pinned by the /simplify review (2026-10-11) ----------------------

from query_translation.oql_lang import parse as _old_parse  # noqa: E402
from query_translation.oqo import Measure, GroupBy  # noqa: E402

_R = {"I141945490": "UBC", "Q48": "Asia", "BR": "Brazil"}.get


def _rt(text):
    return render_core(parse_core(text), lambda v, c=None: _R(str(v)))


@pytest.mark.parametrize("text", [
    "get works since 2020 from [Asia](Q48)",
    "get the count of works about kelp by author at [UBC](I141945490)",
    "get the count of works about kelp by author in [Brazil](BR) since 2022",
    "get authors at [UBC](I141945490) in 2+ years since 2022 with an h-index above 50",
])
def test_review_round_trips(text):
    assert _rt(text) == text


def test_bare_at_means_what_todays_parser_means():
    # `at [UBC]` is any year in both grammars (Jason 2026-10-12: OQL hides no assumptions)
    core = parse_core("get the count of works about kelp by author at [UBC](I141945490)")
    old = _old_parse("get authors at [UBC](I141945490) who published works where "
                     "title-abstract-keywords has kelp; then, summarize each author using count")
    assert core.group_by[0].where == old.group_by[0].where
    assert core.group_by[0].where == parse_core(
        "get the count of works about kelp by author ever at [UBC](I141945490)").group_by[0].where
    assert "since" not in _rt("get the count of works about kelp by author at [UBC](I141945490)")


def test_unnamed_measure_keeps_todays_echo():
    oqo = OQO(get_rows="works", group_by=[GroupBy(column_id="publication_year")],
              calculate=[Measure("max", "cited_by_count")])
    assert render_core(oqo) is None


def test_core_sentence_error_is_cores():
    from query_translation.oql_parser import OQLParseError
    with pytest.raises(OQLParseError) as e:
        parse_oql_to_oqo("get the count of works about by author")
    assert "ends too soon" in str(e.value)


@pytest.mark.parametrize("oxford,plain", [
    ("get the count, sum of citations, and mean FWCI of works about kelp by author. Show h-index.",
     "get the count, sum of citations and mean FWCI of works about kelp by author. Show h-index."),
    ("get works co-authored by [A](A5067184382), [B](A5074743574), and [C](A5047110566)",
     "get works co-authored by [A](A5067184382), [B](A5074743574) and [C](A5047110566)"),
])
def test_oxford_comma_canonical_both_read(oxford, plain):
    # the Oxford comma in the echo (Jason 2026-10-12); the list without it reads the same
    assert parse_core(oxford).to_dict() == parse_core(plain).to_dict()
    assert render_core(parse_core(plain), lambda v, c=None: {"A5067184382": "A", "A5074743574": "B",
                                                            "A5047110566": "C"}.get(str(v))) == oxford


@pytest.mark.parametrize("col", ["topics.id", "topics.subfield.id", "topics.field.id", "topics.domain.id"])
def test_any_topic_never_reads_as_the_primary_topic(col):
    # the echo must not cover a key (Jason 2026-10-12): `in the topic [X]` is the primary
    # topic, so any of a work's topics stays in the `where` form and reads back as itself
    from query_translation.oqo import LeafFilter
    oqo = OQO(get_rows="works", filter_rows=[LeafFilter(col, "T10033" if col == "topics.id" else "17")])
    text = render_core(oqo, lambda v, c=None: "X")
    assert " in the " not in text
    assert parse_core(text).filter_rows[0].column_id == col


# --- the baseline over the page's groups, its switch, and the flip by config (2026-10-12) ---

def test_baseline_lists_the_groups_on_the_page():
    from query_translation.execution import _baseline_on_page_groups
    boqo = OQO(get_rows="works", group_by=[GroupBy(column_id="authorships.countries"),
                                          GroupBy(column_id="open_access.is_oa")])
    page = [{"key": "https://openalex.org/countries/CA",
             "groups": [{"key": "true"}, {"key": "false"}]},
            {"key": "https://openalex.org/countries/US", "groups": [{"key": "true"}]}]
    out = _baseline_on_page_groups(boqo, page)
    assert out.group_by[0].values == ["CA", "US"]
    assert out.group_by[1].values == ["false", "true"]     # sorted: same groups, same request


def test_baseline_leaves_a_level_open_when_a_group_cant_be_named_again():
    from query_translation.execution import _baseline_on_page_groups
    boqo = OQO(get_rows="works", group_by=[GroupBy(column_id="sustainable_development_goals.id")])
    out = _baseline_on_page_groups(boqo, [{"key": "https://openalex.org/sdgs/3"}, {"key": "unknown"}])
    assert out.group_by[0].values is None


def test_a_listed_value_is_named_like_the_plain_split():
    # `13` from a listed split reads `https://openalex.org/fields/13`, as a split by field writes it
    from query_translation.analytics import Level, _row_key
    lv = Level(0, GroupBy(column_id="primary_topic.field.id"), "filters",
               column_id="primary_topic.field.id", group_entity="fields")
    assert _row_key("13", lv, "works") == _row_key(13, lv, "works") == "https://openalex.org/fields/13"


@pytest.mark.parametrize("args,style,want", [
    # held (Jason 2026-10-12): never automatic, in any style; only when asked
    ("", "pipeline", False), ("?oql_style=core", "pipeline", False), ("", "core", False),
    ("?baseline=false", "core", False), ("?baseline=true", "pipeline", True),
])
def test_baseline_switch(monkeypatch, args, style, want):
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.x_query import baseline_wanted
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", style)
    with Flask(__name__).test_request_context("/" + args):
        assert baseline_wanted() is want


def test_the_core_flip_is_a_config_change(monkeypatch):
    # OQL_CANONICAL_STYLE=core: the echo is core where core can say it, else today's pipeline text
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.x_query import build_x_query
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "core")
    core = parse_core("get the count and share of works about kelp by year")
    piped = OQO(get_rows="works", group_by=[GroupBy(column_id="publication_year")],
                calculate=[Measure("max", "cited_by_count")])     # no core name for max
    with Flask(__name__).test_request_context("/"):
        assert build_x_query(core, sort_operands=False)["oql"] == "get the count and share of works about kelp by year"
        assert build_x_query(piped, sort_operands=False)["oql"].startswith("get works;\nthen, group")


# --- both forms everywhere until the flip: x_new_oql beside oql (Jason 2026-10-13) ---

def test_x_query_carries_both_forms(monkeypatch):
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.x_query import build_x_query
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "pipeline")
    core = parse_core("get the count and share of works about kelp by year")
    piped = OQO(get_rows="works", group_by=[GroupBy(column_id="publication_year")],
                calculate=[Measure("max", "cited_by_count")])     # no core name for max
    with Flask(__name__).test_request_context("/"):
        xq = build_x_query(core, sort_operands=False)
        assert xq["oql"].startswith("get works where title-abstract-keywords has")   # the old form stays
        assert xq["x_new_oql"] == "get the count and share of works about kelp by year"
        assert build_x_query(piped, sort_operands=False)["x_new_oql"].startswith("get works;\nthen, group")
    with Flask(__name__).test_request_context("/?oql_style=core"):
        xq = build_x_query(core, sort_operands=False)
        assert xq["oql"] == xq["x_new_oql"] == "get the count and share of works about kelp by year"


def test_query_endpoint_formats_carry_both_forms(monkeypatch):
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.validator import ValidationResult
    from query_translation.views import render_all_formats
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "pipeline")
    with Flask(__name__).test_request_context("/"):
        for oqo in (parse_core("get works about kelp since 2020"),          # plain path
                    parse_core("get the count and share of works about kelp by year")):    # pipeline path
            out = render_all_formats(oqo, ValidationResult(valid=True, errors=[], warnings=[]),
                                     sort_operands=False)
            assert out["oql"] and out["x_new_oql"] and out["oql"] != out["x_new_oql"]
            assert out["x_new_oql"].startswith(("get works since 2020 about kelp", "get the count and share of works"))


def test_the_core_flip_keeps_the_builder_tree(monkeypatch):
    # the website's no-code builder draws `oql_render_v2`; the core echo changes only the text
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.validator import ValidationResult
    from query_translation.views import render_all_formats
    oqo = parse_core("get works about kelp since 2020")
    ok = ValidationResult(valid=True, errors=[], warnings=[])
    with Flask(__name__).test_request_context("/"):
        monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "pipeline")
        before = render_all_formats(oqo, ok, sort_operands=False)
        monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "core")
        after = render_all_formats(oqo, ok, sort_operands=False)
    assert after["oql"] == after["oql_oneline"] == after["x_new_oql"] == before["x_new_oql"]
    assert after["oql_render_v2"] and after["oql_render_v2"] == before["oql_render_v2"]
    assert after["oxurl"] == before["oxurl"]


def test_things_with_key_value_where_round_trip():
    # the echo writes the things' own fields it can't say as `where` (live check, 2026-10-13)
    text = "get authors with an h-index above 50 where last known institution is [UBC](I141945490)"
    assert _rt(text) == text


@pytest.mark.parametrize("c", DATA["cases"], ids=lambda c: str(c["case"]))
def test_x_new_oql_is_a_fixed_point(c):
    # the website's OQL tab reseeds with x_new_oql after each validate, so it must read back
    # to itself, or the tab would flip between two texts (oxjob #1555, 2026-10-13)
    from query_translation.oql_parser import parse_either
    from query_translation.x_query import new_oql
    first = new_oql(OQO.from_dict(c["oqo"]))
    if first is None or "collection" in first:     # collections need the users API
        pytest.skip("no text, or a collection")
    assert new_oql(parse_either(first)) == first


def test_validate_reads_core_sentences():
    # the editor's /validate reads what execute reads, so the new form isn't flagged invalid
    from flask import Flask
    from query_translation.editor_views import blueprint
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    with app.test_client() as client:
        ok = client.get("/validate", query_string={"q": "get the count and share of works about kelp by year"}).get_json()
        assert ok["valid"] and ok["x_new_oql"] == "get the count and share of works about kelp by year"
        assert ok["oql"].startswith("get works where title-abstract-keywords has")
        bad = client.get("/validate", query_string={"q": "get the count of works about by author"}).get_json()
        assert bad["valid"] is False and bad["diagnostics"]
        gone = client.get("/validate", query_string={"q": "break down works about kelp by year"}).get_json()
        assert gone["valid"] is False      # `rank` and `break down` are gone (Jason 2026-10-20)


# --- words for every order (Jason 2026-10-13 via #1658) --------------------------------

from query_translation.oqo import SortBy  # noqa: E402
from query_translation.oqo import LeafFilter as _Leaf  # noqa: E402

_ART = [_Leaf("type", "article")]


@pytest.mark.parametrize("col,d,words", [
    ("referenced_works_count", "desc", "highest reference count first"),
    ("apc_paid.value_usd", "asc", "lowest estimated APC paid first"),
    ("created_date", "desc", "latest created date first"),
    ("open_access.is_oa", "desc", "open access first"),
    ("open_access.is_oa", "asc", "open access last"),
    ("citation_normalized_percentile.is_in_top_1_percent", "desc", "top 1% cited first"),
    ("primary_location.source.id", "asc", "in source ID order"),
    ("display_name", "desc", "reverse alphabetical by title"),
    ("cited_by_count", "desc", "most cited first"),
])
def test_every_sortable_column_has_words(col, d, words):
    text = render_core(OQO(get_rows="works", filter_rows=_ART, sort_by=[SortBy(col, d)]))
    assert text == "get articles, " + words
    assert [(s.column_id, s.direction) for s in parse_core(text).sort_by] == [(col, d)]


def test_the_default_order_is_never_written():
    # works: most cited (age-adjusted) with no search; best matches with one (Jason 2026-10-13)
    from query_translation.oql_core import AGE_ADJUSTED
    assert render_core(OQO(get_rows="works", filter_rows=_ART, sort_by=list(AGE_ADJUSTED))) == "get articles"
    kelp = [_Leaf("title_abstract_keywords.search", "kelp", "has")]
    assert render_core(OQO(get_rows="works", filter_rows=kelp,
                           sort_by=[SortBy("relevance_score", "desc")])) == "get works about kelp"
    # things: most works
    assert render_core(OQO(get_rows="authors", filter_rows=[_Leaf("summary_stats.h_index", 50, ">")],
                           sort_by=[SortBy("works_count", "desc")])) == "get authors with an h-index above 50"


def test_age_adjusted_is_written_when_a_search_makes_best_matches_the_default():
    from query_translation.oql_core import AGE_ADJUSTED
    kelp = [_Leaf("title_abstract_keywords.search", "kelp", "has")]
    text = render_core(OQO(get_rows="works", filter_rows=kelp, sort_by=list(AGE_ADJUSTED)))
    assert text == "get works about kelp, most cited (age-adjusted) first"
    for said in (text, "get works about kelp, most cited for their year first",
                 "get works about kelp, highest citation percentile by year first"):
        assert parse_core(said).sort_by == list(AGE_ADJUSTED)


def test_a_table_sorted_by_count_writes_no_order():
    # most works first is a table's default, whatever numbers it shows (#1658's edge)
    from query_translation.oqo import GroupBy
    oqo = OQO(get_rows="works", filter_rows=[_Leaf("title_abstract_keywords.search", "kelp", "has")],
              group_by=[GroupBy(column_id="authorships.institutions.lineage")],
              calculate=[Measure("mean", "fwci")], sort_by=[SortBy("count", "desc")])
    text = render_core(oqo)
    assert text == "get the mean FWCI of works about kelp by institution"
    assert parse_core(text).sort_by == []


@pytest.mark.parametrize("col,d,tail", [
    ("publication_year", "desc", "by year, newest first"),
    ("authorships.institutions.lineage", "asc", "by institution, in institution ID order"),
    ("type", "desc", "by type, reverse alphabetical by type"),
])
def test_a_table_in_key_order_says_so(col, d, tail):
    # a split's own order, at the end like any order (#1658's edge)
    from query_translation.oqo import GroupBy
    oqo = OQO(get_rows="works", filter_rows=[_Leaf("title_abstract_keywords.search", "kelp", "has")],
              group_by=[GroupBy(column_id=col)], calculate=[Measure("count"), Measure("percent_of_those")],
              sort_by=[SortBy("key", d)])
    text = render_core(oqo)
    assert text == "get the count and share of works about kelp " + tail
    assert [(s.column_id, s.direction) for s in parse_core(text).sort_by] == [("key", d)]


def test_only_count_threshold_is_read_never_dropped():
    # session "1658", 2026-10-13: the `Only` count was silently dropped (all 115 groups)
    text = "get the count of works about kelp by country. Only countries with more than 500 works about kelp."
    o = parse_core(text)
    assert o.group_by[0].where.measure == "count" and o.group_by[0].where.value == 500
    assert render_core(o) == text


@pytest.mark.parametrize("ops, want", [
    ([(">", 1989), ("<", 2000)], "get works from 1990–1999"),    # was `since 1990`: the bound was dropped
    ([("<", 2010)], "get works before 2010"),
    ([(">", 42), ("<", 100)], None),                             # 2-digit years: the general form
    ([("is", 2020), (">=", 2010)], None),
])
def test_every_year_bound_is_said_or_the_sentence_is_not_used(ops, want):
    # corpus row 100 (pre-flip check, 2026-10-22): `year > 42 and year < 100` echoed `get works since 43`
    oqo = OQO(get_rows="works", filter_rows=[_Leaf("publication_year", v, op) for op, v in ops])
    assert render_core(oqo) == want


def test_an_only_floor_on_a_journal_split_says_journal_once():
    # #1494's eval, 2026-10-20: `by journal. Only journals ...` doubled `type: journal` in the
    # split, and the echo fell back to the general form
    text = ("get the count and mean FWCI of works in the topic (T10005) by journal. "
            "Only journals with at least 50 works in the topic (T10005).")
    o = parse_core(text)
    assert [f.to_dict() for f in _and_items(o.group_by[0].where)].count({"column_id": "type", "value": "journal"}) == 1
    assert render_core(o) == text


@pytest.mark.parametrize("q", [
    "get the count of works about kelp by country. Only countries with more than 500 works since 2020.",
    "get the count of works about kelp by country. Only institutions with more than 5 works about kelp.",
    "get works about kelp. Only works with more than 5 citations.",
    "rank countries by count of works about kelp",          # `rank` is gone (Jason 2026-10-20)
    "break down works about kelp by year",                  # so is `break down`
])
def test_an_only_sentence_it_cannot_read_is_refused(q):
    from query_translation.oql_core import NotCore
    with pytest.raises(NotCore):
        parse_core(q)


@pytest.mark.parametrize("dims", ["country and year", "year and country", "country and year since 2020"])
def test_a_breakdown_keeps_its_own_dimension_order(dims):
    # session "1658", 2026-10-13: `by country and year` echoed year-first and read back nested the other way
    text = f"get the count and share of works about kelp by {dims}"
    assert render_core(parse_core(text)) == text


# --- found by the new search page (#1744), 2026-10-20 ---
def test_a_things_own_continent_reads_in_place():
    # `institutions in [Africa]` fell back to the old multi-line form
    oqo = OQO.from_dict({"get_rows": "works", "filter_rows": [{"column_id": "primary_topic.id", "value": "T10091"}],
                         "group_by": [{"column_id": "authorships.institutions.lineage",
                                       "where": {"column_id": "continent", "value": "Q15"}}],
                         "calculate": [{"measure": "count"}],
                         "sort_by": [{"column_id": "count", "direction": "desc"}]})
    text = render_core(oqo, lambda v, c=None: {"Q15": "Africa", "T10091": "Malaria Research and Control"}.get(v))
    assert text == ("get the count of works in the topic [Malaria Research and Control](T10091) by "
                    "institution in [Africa](Q15)")
    back = canonicalize_oqo(parse_core(text), sort_operands=False)
    assert back.group_by[0].where.column_id == "continent" and back.group_by[0].where.value == "Q15"
    assert render_core(back, None) == "get the count of works in the topic (T10091) by institution in [Africa](Q15)"
    assert render_core(parse_core("get institutions in [Africa](Q15)"), None) == "get institutions in [Africa](Q15)"


def test_the_execute_echo_names_entities_in_the_new_form(monkeypatch):
    # meta.x_query.x_new_oql read `get (I63966007)'s works` on POST / while /query named it
    from query_translation import x_query
    batches = []

    def fake(ids):
        batches.append(list(ids))
        return {i: "Massachusetts Institute of Technology" for i in ids if i == "institutions/I63966007"}

    monkeypatch.setattr(x_query, "_batch_names", fake)
    x_query._ECHO_NAMES.clear()
    oqo = parse_core("get [MIT](I63966007)'s works about (quantum computing)")
    xq = x_query.build_x_query(oqo, sort_operands=False, name_new_form=True)
    assert xq["x_new_oql"] == "get [Massachusetts Institute of Technology](I63966007)'s works about (quantum computing)"
    assert x_query.build_x_query(oqo, sort_operands=False)["x_new_oql"].startswith("get (I63966007)'s")
    x_query.build_x_query(oqo, sort_operands=False, name_new_form=True)
    assert batches == [["institutions/I63966007"]]          # one query, then the cache


def test_the_execute_echo_names_many_ids_in_one_query(monkeypatch):
    from query_translation import x_query
    from query_translation.oql_parser import parse_either
    batches = []
    monkeypatch.setattr(x_query, "_batch_names", lambda ids: batches.append(ids) or {i: "Some Place" for i in ids})
    monkeypatch.setattr(x_query, "safe_get_display_name", lambda i: pytest.fail("one-by-one lookup"))
    x_query._ECHO_NAMES.clear()
    ids = [f"I{100 + i}" for i in range(30)]
    oqo = parse_either("get works where authorships.institutions.lineage is (" + " or ".join(ids) + ")")
    oqo = oqo[0] if isinstance(oqo, tuple) else oqo
    text = x_query.build_x_query(oqo, sort_operands=False, name_new_form=True)["x_new_oql"]
    assert len(batches) == 1 and text.count("[Some Place]") == 30 and "no entity found" not in text


def test_a_then_step_after_a_sentence_is_refused_never_dropped():
    # MCP pre-flip audit, 2026-10-22: the step was dropped and the query ran as a plain list
    from query_translation.oql_parser import parse_either
    from query_translation.oql_core import NotCore
    q = "get works about kelp where retracted is (false); then group those works by year"
    with pytest.raises(NotCore):
        parse_core(q)
    with pytest.raises(Exception):
        parse_either(q)


# --- #1589's recheck after the default flip (2026-10-23) ---

@pytest.mark.parametrize("text, echo", [
    # a group's own relation filter is a filter, not a step (the `; then` refusal caught it)
    ("get the count of works about kelp by author where co-author is not [Y](A5023888391)", None),
    # an unknown value reads in the general where clause, never `from (None)`
    ("get works from 2024 about kelp where institution is unknown",
     "get works from 2024 about kelp where institution is unknown"),
    # `never at` in words; its general form leaked the column id
    ("get authors never at [UBC](I141945490)", "get authors never at (I141945490)"),
    ("get authors at [UBC](I141945490) never in [Brazil](BR)", "get authors at (I141945490) never in [Brazil](BR)"),
    # `cited by [W]` (core spec § 2.6), beside `citing`
    ("get works cited by [W](W2741809807)", "get works cited by (W2741809807)"),
    # named authors or journals as a split (#1494's gap 1)
    ("get the count of works about kelp by author in ([A](A5023888391), [B](A5067184382))",
     "get the count of works about kelp by author in ((A5023888391), (A5067184382))"),
    ("get the count of works about kelp by journal in ([N](S137773608), [S](S3880285))",
     "get the count of works about kelp by source in ((S137773608), (S3880285))"),
])
def test_forms_found_after_the_default_flip_read_and_round_trip(text, echo):
    from query_translation.oql_parser import parse_either
    from query_translation.oqo_canonicalizer import canonicalize_oqo as canon
    from query_translation.x_query import new_oql
    o = parse_either(text)
    e = new_oql(o)
    if echo is not None:
        assert e == echo
    assert canon(parse_either(e)).to_dict() == canon(o).to_dict()
