"""Walks and sets in the pipeline language (oxjob #1535): parse, render, types,
validation and the pure parts of the executor. The live checks (every #1512 walk
example against an independent ES computation) are in the job:
oxjobs working/oql-walks-and-sets-rung-2/work/scripts/verify_walks.py."""
import pytest

from query_translation import walk_exec as W
from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse, render
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo import OQO, LeafFilter, result_entity
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.validator import validate_oqo
from query_translation.walks import possessive, walk_state


def _line(q):
    return render_pipeline_line(canonicalize_oqo(parse(q), sort_operands=False))


def _err(q):
    with pytest.raises(OQLError) as e:
        parse(q)
    return e.value


# ---------------------------------------------------------------------------
# Parse and render
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "get works where institution is (I63966007); then get each author of those works",
    "get works where topic is (T10878); then get authors of those works; then calculate count",
    "get works where year >= (2020); then get each funder of those works; "
    "then get all that funder's works; then calculate mean citation count",
    "get works where year >= (2020); then get SDGs of those works",
    "get works where year >= (2020); then get each SDG of those works; "
    "then get all that SDG's works where year >= (2024); then calculate count",
    "get works where title has (kelp); then get authors of those works; "
    "then get all those authors' works; then group those works by year; then calculate count",
    "get authors where h-index > (50); then get all those authors' works; then calculate count",
    "get works where it's cited by works in (get works where institution is (I146416000))",
    "get works where it isn't cited by works in (get works where institution is (I146416000))",
    "get works where institution is not in (get works where title has (kelp); "
    "then get institutions of those works)",
])
def test_round_trip(q):
    assert _line(q) == q
    assert _line(_line(q)) == q


def test_walk_oqo_shape():
    o = parse("get works where title-abstract has (kelp); then get each author of those works "
              "where h-index > (20); then get all that author's works; then calculate count")
    assert o.to_dict()["walks"] == [
        {"column_id": "authorships.author.id", "each": True,
         "where": {"column_id": "summary_stats.h_index", "value": 20, "operator": ">"}},
        {"to": "works"}]
    assert result_entity(o) == "works"
    assert walk_state(o) == ("works", True, "authorships.author.id")


def test_noun_links_follow_the_filter_words():
    # source = journal of record, topic = primary topic, institution = with parents
    o = parse("get works where year > (2020); then get each source of those works")
    assert o.walks[0].column_id == "primary_location.source.id"
    o = parse("get works where year > (2020); then get topics of those works")
    assert o.walks[0].column_id == "primary_topic.id"
    o = parse("get works where year > (2020); then get each institution of those works")
    assert o.walks[0].column_id == "authorships.institutions.lineage"


def test_optional_of_those_works_on_input():
    assert _line("get works where year > (2020); then get each author") == \
        "get works where year > (2020); then get each author of those works"


def test_possessives():
    assert possessive("authors", True) == "that author's"
    assert possessive("authors", False) == "those authors'"
    assert possessive("sdgs", False) == "those SDGs'"
    assert possessive("countries", True) == "that country's"


def test_verb_negation_of_relations_folds():
    assert _line("get works where it does not cite works in (get works where year is (2020))") \
        == "get works where it doesn't cite works in (get works where year is (2020))"


# ---------------------------------------------------------------------------
# Loud errors, each with a fix
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q,code", [
    ("get works where year > (2020); then group those works by year; "
     "then get each author of those works", "OQL_WALK_AFTER_SPLIT"),
    ("get works where year > (2020); then get each authors of those works", "OQL_BAD_WALK_NOUN"),
    ("get works where year > (2020); then get author of those works", "OQL_BAD_WALK_NOUN"),
    ("get works where year > (2020); then get each paper of those works", "OQL_BAD_WALK_NOUN"),
    ("get works where year > (2020); then get all that author's works", "OQL_NOTHING_TO_WALK_BACK"),
    ("get works where year > (2020); then get each author of those works; "
     "then get all those authors' works", "OQL_WRONG_SET"),
    ("get works where year > (2020); then get each author of those works; "
     "then get each source of those authors", "OQL_WALK_FROM_THINGS"),
    ("get works where year > (2020); then get each author of those works; "
     "then get all that author's works; then get each source of those works",
     "OQL_ONE_WALK_OUT"),
    ("get works where year > (2020); then get each country of those works where x is (y)",
     "OQL_WALK_WHERE_NOT_AVAILABLE"),
    ("get each work in (W1)", "OQL_EACH_WORK"),
    ("get works where author is in (get works where year is (2020)", "OQL_UNCLOSED_QUERY"),
    ("get works where author is in (get works where it cites works in "
     "(get works where year is (2020)); then get authors of those works)",
     "OQL_NESTED_QUERY_DEPTH"),
])
def test_errors(q, code):
    e = _err(q)
    assert e.code == code
    assert e.fixit


def test_wrong_type_set_carries_the_whole_fixed_query():
    # ACCEPTANCE 4: names the types and carries the fixed whole query (both readings)
    q = ("get works where it cites works in (get works where title has (kelp); "
         "then get each author of those works); then group those works by country")
    e = _err(q)
    assert e.code == "OQL_QUERY_SET_TYPE"
    assert "takes works" in e.message and "returns authors" in e.message
    assert ("for the works themselves: get works where it cites works in "
            "(get works where title has (kelp)); then group those works by country") in e.fixit
    assert ("then get all those authors' works); then group those works by country"
            in e.fixit)
    for reading in e.fixit.split(" | "):
        parse(reading.split(": ", 1)[1])          # each fix runs as is


def test_works_where_authors_wanted():
    e = _err("get works where author is in (get works where title has (kelp)) and year > (2024)")
    assert e.fixit == ("for the authors of those works: get works where author is in "
                       "(get works where title has (kelp); then get authors of those works) "
                       "and year > (2024)")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _v(d):
    return validate_oqo(OQO.from_dict(d))


def test_validator_accepts_the_examples():
    for q in ["get works where institution is (I63966007); then get each author of those "
              "works; then get all that author's works; then calculate mean FWCI",
              "get works where it cites works in (get works where institution is "
              "(I146416000)); then group those works by country; then calculate count",
              "get authors where h-index > (50); then get all those authors' works; then "
              "group those works by year; then calculate count"]:
        assert validate_oqo(parse(q)).valid, q


@pytest.mark.parametrize("d,loc", [
    ({"get_rows": "works", "walks": [{"column_id": "fwci", "each": True}]}, "walks[0].column_id"),
    ({"get_rows": "works", "walks": [{"to": "works"}]}, "walks[0]"),
    ({"get_rows": "works", "walks": [{"column_id": "authorships.author.id", "each": True,
                                      "where": {"column_id": "fwci", "value": 2,
                                                "operator": ">"}}]}, "walks[0].where.column_id"),
    ({"get_rows": "works", "walks": [{"column_id": "authorships.author.id", "each": True}],
      "calculate": [{"measure": "count"}]}, "calculate"),
    ({"get_rows": "works", "walks": [{"column_id": "authorships.author.id", "each": False}],
      "calculate": [{"measure": "mean", "column_id": "fwci"}]}, "calculate"),
    ({"get_rows": "works", "filter_rows": [{"column_id": "authorships.author.id",
                                            "operator": "in", "value": {"get_rows": "works"}}]},
     "filter_rows[0].value"),
    ({"get_rows": "works", "filter_rows": [{"column_id": "referenced_works", "operator": "in",
                                            "value": {"get_rows": "works", "calculate":
                                                      [{"measure": "count"}]}}]},
     "filter_rows[0].value"),
])
def test_validator_refusals(d, loc):
    r = _v(d)
    assert not r.valid
    assert any(e.location == loc for e in r.errors), r.to_dict()


# ---------------------------------------------------------------------------
# Executor, pure parts
# ---------------------------------------------------------------------------
def test_needs_walk():
    assert W.needs_walk(parse("get works where year > (2020); then get authors of those works"))
    assert W.needs_walk(parse("get works where it cites works in (get works where year is (2020))"))
    assert W.needs_walk(parse("get each institution in (I1, I2)"))
    assert not W.needs_walk(parse("get works where year > (2020); then group those works by year"))


def test_listed_ids_of_an_each_start():
    o = parse("get each institution in (I63966007, I97018004)")
    assert W._listed_ids(o) == ["https://openalex.org/I63966007", "https://openalex.org/I97018004"]
    assert W._listed_ids(parse("get authors where h-index > (50)")) is None


def test_idset_translates_to_chunked_terms_and_echoes_small():
    from query_translation.oqo_to_es import _translate
    from works.fields import fields_dict
    ids = [f"https://openalex.org/A{i}" for i in range(130_000)]
    leaf = LeafFilter("authorships.author.id", W.IdSet(ids, "get works ...; then get authors"), "in")
    q = _translate(leaf, fields_dict).to_dict()
    clauses = q["bool"]["should"]
    assert len(clauses) == 3 and sum(len(c["terms"]["authorships_full.author.id"])
                                     for c in clauses) == 130_000
    assert leaf.to_dict()["value"] == {"ids_of": "get works ...; then get authors", "count": 130_000}
    neg = _translate(LeafFilter("ids.openalex", W.IdSet(["https://openalex.org/W1"], "x"), "in",
                                is_negated=True), fields_dict).to_dict()
    assert neg == {"bool": {"must_not": [{"terms": {"id": ["https://openalex.org/W1"]}}]}}


def test_walk_price_counts_the_calls():
    o = parse("get works where title has (kelp); then get authors of those works; "
              "then calculate count")
    p = W.walk_price(o, 7)
    assert p["credits"] == 10 + 6
    assert p["steps"][-1]["what"] == "walks and sets: 6 more calls"


def test_a_walk_that_ends_at_the_things_lists_them_as_rung_1_splits():
    # no ES needed: the plan hands Rung 1 a split by the walked column
    kind, oqo = W.prepare(parse("get works where year > (2020); then get each author of "
                                "those works where h-index > (20)"), "walden", None)
    assert kind == "oqo"
    assert [g.to_dict() for g in oqo.group_by] == [{
        "column_id": "authorships.author.id",
        "where": {"column_id": "summary_stats.h_index", "value": 20, "operator": ">"}}]
    assert [m.measure for m in oqo.calculate] == ["count"] and not oqo.walks
