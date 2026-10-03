"""The pipeline language (oxjob #1530; spec #1512 SYNTAX.md and work/oql_draft.md).

`get works where ...; then group those works by ...; then calculate ...` parses to
OQO splits (`group_by`) and a `calculate` list, renders back in the pipeline style,
and every limit or type slip is a loud error with a fix.
"""
import os

import pytest
import yaml

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse, render
from query_translation.oqo import OQO, GroupBy, Measure, MeasureFilter
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "oql", "corpus.yaml")


def _canon(q):
    return canonicalize_oqo(parse(q))


def _flat(text):
    """The one-line form of a (possibly multi-line) canonical render."""
    return " ".join(text.replace(";\nthen ", "; then ").split())


# The #1512 examples that don't walk (work/oql_draft.md 1-3, 6, 9, 10, 13-17; ids
# for names). Each is already canonical, so it must echo itself.
EXAMPLES = [
    "get works where country is (KE) and year >= (2015); then group those works by year; "
    "then calculate percent open access",
    "get works where institution is (I63966007); then group those works by open access "
    "status; then calculate count, mean FWCI",
    "get works where institution is (I63966007); then group those works by author; then "
    "calculate mean FWCI",
    "get works where title-abstract has (kelp); then group those works by author where "
    "count of those works > (10) and co-author is not (A5023888391)",
    'get works where year >= (2010); then group those works by title-abstract search in '
    '(("inference latency"), ("neuromorphic computing"), ("edge AI")); then group those '
    'works again by year; then calculate count',
    "get works where topic is (T10878); then group those works by institution in "
    "(I63966007, I97018004, I136199984); then calculate count, mean FWCI, percent open access",
    "get works where country is (KE) and year >= (2015); then group those works by funder; "
    "then calculate count, mean citation count",
    "get works where topic is in (col_abc123); then group those works by institution where "
    "collaborator is not (I63966007); then calculate count",
    "get works where year >= (2016); then group those works into ((institution is "
    "(I99464096)), (country is (BE))); then group those works again by SDG; then calculate "
    "count, percent of those works",
    "get works where institution is in (col_abc123); then group those works into ((year >= "
    "(2016) and year <= (2019)), (year >= (2021))); then group those works again by topic; "
    "then calculate count",
]


@pytest.mark.parametrize("q", EXAMPLES)
def test_example_echoes_itself(q):
    oqo = _canon(q)
    assert oqo.uses_pipeline
    assert _flat(render(oqo)) == q


@pytest.mark.parametrize("q", EXAMPLES)
def test_example_round_trips(q):
    oqo = _canon(q)
    assert _canon(render(oqo)).to_dict() == oqo.to_dict()
    assert OQO.from_dict(oqo.to_dict()).to_dict() == oqo.to_dict()


def test_example_15_plain_authors_query_stays_classic_until_launch():
    q = "get authors where last known institution is (I136199984) and h-index > (50)"
    oqo = _canon(q)
    assert not oqo.uses_pipeline
    assert render(oqo) == ("authors where last known institution is (I136199984) "
                           "and h-index > (50)")
    assert render(oqo, style="pipeline") == q


def test_oqo_shape():
    oqo = _canon(EXAMPLES[3])
    g = oqo.group_by[0]
    assert g.column_id == "authorships.author.id"
    assert isinstance(g.where.filters[1], MeasureFilter) or isinstance(
        g.where.filters[0], MeasureFilter)
    assert {f.to_dict().get("column_id") for f in g.where.filters} >= {"co_author"}
    oqo = _canon(EXAMPLES[1])
    assert oqo.calculate == [Measure("count"), Measure("mean", "fwci")]
    assert [m.key for m in oqo.calculate] == ["count", "mean_fwci"]


def test_bins_and_values():
    oqo = _canon("get works where institution is (I1); then group those works into "
                 "citation count bins at (1, 10, 100); then group those works again into "
                 "FWCI bins of (0.5)")
    assert oqo.group_by[0] == GroupBy(column_id="cited_by_count", bins={"at": [1, 10, 100]})
    assert oqo.group_by[1] == GroupBy(column_id="fwci", bins={"of": 0.5})
    assert _flat(render(oqo)) == (
        "get works where institution is (I1); then group those works into citation count "
        "bins at (1, 10, 100); then group those works again into FWCI bins of (0.5)")


@pytest.mark.parametrize("typed,canonical", [
    # `again`, `those works`, `;` are optional on input; canonical adds them
    ("get works where year > (2020) then group by year then group by type",
     "get works where year > (2020); then group those works by year; then group those "
     "works again by type"),
    # the classic group-by plus a calculation
    ("works where year > 2020 group by year; then calculate count",
     "get works where year > (2020); then group those works by year; then calculate count"),
    ("get works where year > (2020); then group by year; then calculate average FWCI and "
     "number of works",
     "get works where year > (2020); then group those works by year; then calculate mean "
     "FWCI, count"),
    # on author groups, `author is ...` can only mean each group's own author
    ("get works where year > (2020); then group those works by author where author is "
     "not in (col_abc)",
     "get works where year > (2020); then group those works by author where that author "
     "is not in (col_abc)"),
])
def test_lenient_input_renders_canonical(typed, canonical):
    assert _flat(render(_canon(typed), style="pipeline")) == canonical


def test_the_launch_switch_renders_every_query_as_a_pipeline(monkeypatch):
    # the launch sets OQL_CANONICAL_STYLE=pipeline (read into CANONICAL_STYLE)
    from query_translation import oql_lang
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "pipeline")
    assert _flat(render(_canon("works where year >= 2020 group by year, type"))) == (
        "get works where year >= (2020); then group those works by year; then group "
        "those works again by type")
    assert render(_canon("works where type is not (review)")) == (
        "get works where type is not (review)")


def test_a_plain_query_in_the_pipeline_style_keeps_its_url_and_builder_tree(monkeypatch):
    # the website's builder reads oql_render_v2; the flip changes only the text, and a
    # plain query keeps today's executor, so it gets no pipeline check (#1536)
    from flask import Flask
    from query_translation import oql_lang
    from query_translation.validator import ValidationResult
    from query_translation.views import render_all_formats
    monkeypatch.setattr(oql_lang, "CANONICAL_STYLE", "pipeline")
    oqo = parse("works where year >= 1976 group by topic, year")
    with Flask(__name__).test_request_context("/"):
        out = render_all_formats(oqo, ValidationResult(valid=True, errors=[], warnings=[]),
                                 sort_operands=False)
    assert out["oql_oneline"] == (
        "get works where year >= (1976); then group those works by topic; then group "
        "those works again by year")
    assert out["oql_render_v2"]["lines"]
    assert out["oxurl"].startswith("/works?")
    assert "check" not in out and out["validation"]["errors"] == []


def test_classic_queries_render_classic():
    assert render(_canon("works where year >= 2020 group by year, type")) == (
        "works where year >= (2020) group by year, type")


@pytest.mark.parametrize("typed,pipeline", [
    ("works where type is not (review)", "get works where type is not (review)"),
    ("works where institution is (not I1 and not I2)",
     "get works where institution is not (I1 or I2)"),
    ("works where institution is not in collection (col_abc)",
     "get works where institution is not in (col_abc)"),
    ("works where title-abstract has ((asthma OR wheeze) NOT (pediatric OR child))",
     "get works where title-abstract has ((asthma OR wheeze) NOT (child OR pediatric))"),
    ("works where year >= 2020 sample 100 seed 4",
     "get works where year >= (2020); then sample (100) of those works with seed (4)"),
])
def test_pipeline_style(typed, pipeline):
    oqo = _canon(typed)
    assert _flat(render(oqo, style="pipeline")) == pipeline
    assert _canon(pipeline).to_dict() == oqo.to_dict()


def test_in_sets():
    assert _canon("get works where institution is in (I1, I2)").to_dict() == \
        _canon("works where institution is (I1 or I2)").to_dict()
    assert _canon("get works where topic is in (col_x)").filter_rows[0].operator == \
        "in collection"


def test_every_corpus_row_round_trips_in_pipeline_style():
    rows = yaml.safe_load(open(CORPUS))["rows"]
    n = 0
    for r in rows:
        q = r.get("oql")
        try:
            oqo = _canon(q) if q else None
        except Exception:
            continue
        if oqo is None:
            continue
        out = render(oqo, style="pipeline")
        assert _canon(out).to_dict() == oqo.to_dict(), (r["id"], q, out)
        n += 1
    assert n > 100


# -- loud errors with fixes (ACCEPTANCE test 3) ----------------------------------
def _err(q):
    with pytest.raises(OQLError) as ei:
        parse(q)
    e = ei.value
    assert e.fixit, e.code
    return e


def test_fourth_split():
    e = _err("get works where year > (2020); then group those works by year; then group "
             "those works again by type; then group those works again by language; then "
             "group those works again by country")
    assert e.code == "OQL_TOO_MANY_SPLITS" and "3" in e.message


def test_list_over_100():
    ids = ", ".join(f"I{i}" for i in range(1, 102))
    e = _err(f"get works where year > (2020); then group those works by institution in ({ids})")
    assert e.code == "OQL_LIST_TOO_LONG" and "100" in e.message


def test_search_over_5_operators():
    e = _err('get works where year > (2020); then group those works by title-abstract '
             'search in ((a OR b OR c OR d OR e OR f OR g))')
    assert e.code == "OQL_SEARCH_TOO_COMPLEX" and "5" in e.message


def test_search_at_5_operators_is_fine():
    parse('get works where year > (2020); then group those works by title-abstract '
          'search in ((a OR b OR c OR d OR e OR f))')


def test_decimal_needs_bins():
    e = _err("get works where year > (2020); then group those works by FWCI")
    assert e.code == "OQL_DECIMAL_NEEDS_BINS" and "bins" in e.fixit


def test_wrong_set_noun():
    e = _err("get works where year > (2020); then group those authors by year")
    assert e.code == "OQL_WRONG_SET" and "those works" in e.fixit


def test_walk_parses_since_rung_2():
    # walks shipped in oxjob #1535 (tests/oql/test_walks.py has the rest)
    o = parse("get works where year > (2020); then get each author of those works")
    assert [w.to_dict() for w in o.walks] == [
        {"column_id": "authorships.author.id", "each": True}]


def test_step_after_calculate():
    e = _err("get works where year > (2020); then calculate count; then group those works "
             "by year")
    assert e.code == "OQL_STEP_AFTER_CALCULATE"


@pytest.mark.parametrize("q,code", [
    ("get works where year > (2020); then calculate mean type", "OQL_BAD_MEASURE"),
    ("get works where year > (2020); then calculate percent year", "OQL_BAD_MEASURE"),
    ("get works where year > (2020); then calculate total", "OQL_BAD_MEASURE"),
    ("get works where year > (2020); then group those works by year where h-index > (20)",
     "OQL_BAD_GROUP_FILTER"),
    ("get works where year > (2020); then group those works by institution where "
     "co-author is not (A1)", "OQL_BAD_GROUP_FILTER"),
    ("get works where year > (2020); then group those works by author where count of "
     "those works > (x)", "OQL_BAD_NUMBER"),
    ("get works where year > (2020); then group those works into type bins at (1, 2)",
     "OQL_BAD_BINS"),
    ("get works where year > (2020); then group those works into citation count bins at "
     "(10, 1)", "OQL_BAD_BINS"),
    ("get works where year > (2020); then frobnicate", "OQL_UNKNOWN_STEP"),
])
def test_more_loud_errors(q, code):
    assert _err(q).code == code


def test_a_groups_own_field_in_calculate():
    # the same reading a group filter gives a non-calculation field: the group's own value
    q = ("get works where source is (S137773608); then group those works by author; then "
         "calculate count, h-index, works count")
    oqo = _canon(q)
    assert oqo.calculate[1] == Measure("value", "summary_stats.h_index")
    assert oqo.calculate[1].key == "summary_stats_h_index"
    assert _flat(render(oqo)) == q
    from query_translation.validator import validate_oqo
    assert validate_oqo(oqo).valid


def test_a_field_of_both_needs_a_calculation():
    # works and authors both have a citation count: ambiguous, so it needs mean / sum
    e = _err("get works where year > (2020); then group those works by author; then "
             "calculate citation count")
    assert e.code == "OQL_BAD_MEASURE" and "mean citation count" in e.fixit


def test_own_field_without_a_split_of_those_things():
    e = _err("get works where year > (2020); then calculate count, h-index")
    assert e.code == "OQL_BAD_MEASURE" and "group those works by author" in e.fixit


def test_min_max_date():
    q = ("get works where year > (2020); then group those works by publisher; then "
         "calculate count, max date, min date")
    oqo = _canon(q)
    assert [m.measure for m in oqo.calculate] == ["count", "max", "min"]
    assert _flat(render(oqo)) == q
    from query_translation.validator import validate_oqo
    assert validate_oqo(oqo).valid


def test_a_field_with_no_split_says_how_to_list_instead():
    # `get sources where ...; then calculate 2-year mean citedness` usually wants the list
    e = _err("get authors where h-index > (50); then calculate h-index")
    assert e.code == "OQL_BAD_MEASURE" and "drop the calculate step" in e.fixit
    e = _err("get works where year > (2020); then group those works by year; then "
             "calculate citation count")
    assert "drop the calculate step" not in e.fixit


def test_mean_of_a_date_is_an_error():
    assert _err("get works where year > (2020); then calculate mean date").code == "OQL_BAD_MEASURE"


def test_wrong_type_id_is_a_validation_error():
    from query_translation.validator import validate_oqo
    r = validate_oqo(_canon("get works where year > (2020); then group those works by "
                            "institution in (A5023888391, I63966007)"))
    assert not r.valid
    assert any("institutions ID" in e.message for e in r.errors)


def test_validator_accepts_examples():
    from query_translation.validator import validate_oqo
    for q in EXAMPLES:
        r = validate_oqo(_canon(q))
        assert r.valid, (q, [e.message for e in r.errors])
