"""Facts about one authorship (oxjob #2537): one person's place on one work.

`get works with [Jane Smith](A5023888391) in the role [Software](software)` keeps only works
where Jane's own authorship carries the role (a flat filter pairs nothing: Jane is on it,
someone did the software); `get the count of works about kelp by author listing [UBC](I141945490)
on the work` counts, for each person, the works where that person listed UBC. Run:
    PYTHONPATH=. pytest tests/oql/test_same_authorship.py -q --noconftest
"""
import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation import same_authorship as SA  # noqa: E402
from query_translation.oql_core import parse_core, render_core  # noqa: E402
from query_translation.oqo import (OQO, PERSON_COLUMN, PLACE_COLUMN, ROLE_COLUMN, AuthorshipFilter,  # noqa: E402
                                   GroupBy, LeafFilter)
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.validator import validate_oqo  # noqa: E402

NAMES = {"A5023888391": "Jane Smith", "I141945490": "UBC"}
PERSON, INST, ROLE = PERSON_COLUMN, PLACE_COLUMN, ROLE_COLUMN

CANONICAL = [
    "get works with [Jane Smith](A5023888391) in the role [Software](software)",
    "get works with [Jane Smith](A5023888391) in the roles [Data curation](data-curation) and [Software](software)",
    "get works with [Jane Smith](A5023888391) in the roles [Data curation](data-curation), "
    "[Methodology](methodology), and [Software](software)",
    "get works with [Jane Smith](A5023888391) listing [UBC](I141945490) on the work",
    "get works about kelp with an author listing [UBC](I141945490) on the work in the role [Software](software)",
    "get works since 2020 about kelp with an author in the role [Software](software)",
    "get the count of works about kelp by author in the role [Data curation](data-curation)",
    "get the count of works about kelp by author listing [UBC](I141945490) on the work",
    "get the count of works about kelp by author listing [UBC](I141945490) on the work in the role "
    "[Software](software)",
]


def _resolver(value, column=None):
    return NAMES.get(str(value))


def _parse(text):
    return canonicalize_oqo(parse_core(text), sort_operands=False)


@pytest.mark.parametrize("text", CANONICAL)
def test_canonical_text_is_a_fixed_point(text):
    assert render_core(_parse(text), _resolver) == text


def test_the_works_form_is_one_condition_on_one_authorship():
    oqo = _parse(CANONICAL[0])
    assert oqo.filter_rows == [AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"),
                                                         LeafFilter(ROLE, "software")])]
    assert oqo.to_dict()["filter_rows"] == [{"same_authorship": [
        {"column_id": PERSON, "value": "A5023888391"}, {"column_id": ROLE, "value": "software"}]}]
    assert OQO.from_dict(oqo.to_dict()) == oqo


def test_the_people_form_is_a_split_by_author_with_conditions_on_the_work():
    oqo = _parse(CANONICAL[7])
    assert oqo.group_by == [GroupBy(column_id=PERSON, same_authorship=[LeafFilter(INST, "I141945490")])]
    assert OQO.from_dict(oqo.to_dict()) == oqo


def test_listing_on_the_work_is_not_the_profile():
    """`at [UBC]` reads the person's profile; `listing [UBC] on the work`, that work's byline."""
    at = _parse("get the count of works about kelp by author at [UBC](I141945490) since 2022")
    on = _parse(CANONICAL[7])
    assert at.group_by[0].where is not None and at.group_by[0].same_authorship is None
    assert on.group_by[0].where is None and on.group_by[0].same_authorship


def test_role_order_and_id_forms_canonicalize():
    a = _parse("get works with [Jane Smith](A5023888391) in the roles [Software](software) and "
               "[Data curation](data-curation)")
    b = canonicalize_oqo(OQO.from_dict({"get_rows": "works", "filter_rows": [{"same_authorship": [
        {"column_id": ROLE, "value": "https://openalex.org/contributor-roles/data-curation"},
        {"column_id": ROLE, "value": "contributor-roles/software"},
        {"column_id": PERSON, "value": "https://openalex.org/A5023888391"}]}]}))
    assert a.to_dict() == b.to_dict()


def test_one_place_alone_is_the_plain_works_filter():
    """One fact pairs nothing: `with an author listing [UBC] on the work` is `from [UBC]`."""
    oqo = _parse("get works about kelp with an author listing [UBC](I141945490) on the work")
    assert LeafFilter(INST, "I141945490") in oqo.filter_rows
    assert not any(isinstance(f, AuthorshipFilter) for f in oqo.filter_rows)


def test_a_role_alone_needs_no_check():
    node = AuthorshipFilter(filters=[LeafFilter(ROLE, "software")])
    assert not node.pairs and not SA.needs_check(node)
    pair = AuthorshipFilter(filters=[LeafFilter(PERSON, "A1"), LeafFilter(ROLE, "software")])
    assert pair.pairs and SA.needs_check(pair)


def test_corresponding_author_still_reads_as_before():
    text = "get works with [Jane Smith](A5023888391) as corresponding author"
    assert _parse(text).filter_rows == [LeafFilter("corresponding_author_ids", "A5023888391")]
    assert render_core(_parse(text), _resolver) == text


# --- the check on one authorship -------------------------------------------------
JANE, UBC = "https://openalex.org/A5023888391", "https://openalex.org/I141945490"
SOFTWARE = "https://openalex.org/contributor-roles/software"


def _seat(author, roles=(), lineage=()):
    return {"author": {"id": author}, "contributor_roles": [{"id": r} for r in roles],
            "institutions": [{"lineage": list(lineage)}]}


def test_the_same_authorship_must_carry_every_fact():
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    coauthor_did_it = [_seat(JANE), _seat("https://openalex.org/A9", [SOFTWARE])]
    jane_did_it = [_seat(JANE, [SOFTWARE]), _seat("https://openalex.org/A9")]
    match = SA.matcher(node)
    assert not any(match(s) for s in coauthor_did_it)
    assert any(match(s) for s in jane_did_it)


def test_institutions_match_by_lineage():
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(INST, "I141945490")])
    department = _seat(JANE, lineage=["https://openalex.org/I999", UBC])
    elsewhere = _seat(JANE, lineage=["https://openalex.org/I999"])
    match = SA.matcher(node)
    assert match(department) and not match(elsewhere)


def test_the_superset_names_every_fact_on_authorships_full():
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    assert SA.superset_query(node) == {"bool": {"filter": [
        {"term": {"authorships_full.author.id": JANE}},
        {"term": {"authorships_full.contributor_roles.id": SOFTWARE}}]}}


class _Ctx:
    """Answers the count (all in one year), then the candidates."""

    def __init__(self, n, seats, hits=()):
        self.n, self.seats, self.hits, self.bodies = n, seats, list(hits), []

    def search(self, body, what, index=None):
        self.bodies.append(body)
        if body.get("size") == 0:
            return {"hits": {"total": {"value": self.n}}, "aggregations": {
                "seats": {"value": self.seats}, "years": {"buckets": [{"key": 2020, "doc_count": self.n}]}}}
        return {"hits": {"hits": self.hits}}


_ANY = AuthorshipFilter(filters=[LeafFilter(ROLE, "software")])


def test_past_the_works_cap_the_refusal_says_how_to_narrow():
    from query_translation.analytics import AnalyticsError
    with pytest.raises(AnalyticsError) as e:
        SA.scan(_Ctx(SA.CANDIDATE_LIMIT + 1, 10), None, _ANY, "x", lambda w, s: w)
    assert e.value.code == "too_many_works_to_check" and "Narrow" in e.value.fix


def test_past_the_authors_cap_hyperauthored_works_are_refused():
    from query_translation.analytics import AnalyticsError
    with pytest.raises(AnalyticsError) as e:
        SA.scan(_Ctx(300, SA.SEAT_LIMIT + 1), None, _ANY, "x", lambda w, s: w)
    assert e.value.code == "too_many_authors_to_check" and "authors count" in e.value.fix


def test_matching_works_keeps_only_works_where_one_authorship_has_both():
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    hits = [{"_source": {"id": "https://openalex.org/W1", "authorships_full": [_seat(JANE, [SOFTWARE])]}},
            {"_source": {"id": "https://openalex.org/W2", "authorships_full": [
                _seat(JANE), _seat("https://openalex.org/A9", [SOFTWARE])]}}]
    ctx = _Ctx(2, 3, hits)
    assert SA.matching_works(ctx, node, None) == ["https://openalex.org/W1"]
    # one count, then one page
    assert len(ctx.bodies) == 2


# --- validation ------------------------------------------------------------------
@pytest.mark.parametrize("oqo,why", [
    ({"get_rows": "works", "filter_rows": [{"same_authorship": [{"column_id": ROLE, "value": "dancing"}]}]},
     "not a contributor role"),
    ({"get_rows": "works", "filter_rows": [{"same_authorship": [{"column_id": "publication_year", "value": 2020}]}]},
     "takes the person"),
    ({"get_rows": "authors", "filter_rows": [{"same_authorship": [{"column_id": ROLE, "value": "software"}]}]},
     "filter works"),
    ({"get_rows": "works", "filter_rows": [{"same_authorship": [{"column_id": ROLE, "value": "software"}],
                                            "is_negated": True}]}, "negated"),
    ({"get_rows": "works", "filter_rows": [{"same_authorship": [{"column_id": INST, "value": "A1"}]}]},
     "not an institution ID"),
    ({"get_rows": "works", "group_by": [{"column_id": "publication_year", "same_authorship": [
        {"column_id": INST, "value": "I141945490"}]}]}, "split works by author"),
    ({"get_rows": "works", "group_by": [{"column_id": PERSON, "same_authorship": [
        {"column_id": INST, "value": "I141945490"}]}], "calculate": [{"measure": "mean", "column_id": "cited_by_count"}]},
     "counts works"),
])
def test_validation_refuses_what_cant_run(oqo, why):
    errors = validate_oqo(OQO.from_dict(oqo)).errors
    assert any(why in e.message for e in errors), [e.message for e in errors]


@pytest.mark.parametrize("text", CANONICAL)
def test_canonical_queries_validate(text):
    assert validate_oqo(_parse(text)).errors == []


# --- the editor's suggestions ------------------------------------------------------
def _suggest(text):
    from query_translation.oql_context import parse_context
    return [s["value"] for s in parse_context(text, len(text))["context"].get("suggestions", [])]


def test_the_editor_offers_the_authorship_words():
    assert {"as corresponding author", "listing", "in the role"} <= set(_suggest(
        "get works with [Jane Smith](A5023888391) "))
    assert {"listing", "in the role"} <= set(_suggest("get works about kelp with an author "))
    assert "on the work" in _suggest("get works with [Jane Smith](A5023888391) listing [UBC](I141945490) ")
    assert {"listing", "in the role"} <= set(_suggest("get the count of works about kelp by author "))


# --- what the outside reviews asked for (23 Nov) -------------------------------------
@pytest.mark.parametrize("text", [
    "get the count of works about kelp by author in the roles [Data curation](data-curation) and [Software](software)",
    "get the count of works about kelp by author listing [Harvard](I136199984) and [UBC](I141945490) on the work",
    "get works with [Jane Smith](A5023888391) in the role [Software](software) "
    "with [Bob](A5000000001) in the role [Data curation](data-curation)",
    "get works with [Jane Smith](A5023888391) as corresponding author "
    "with [Jane Smith](A5023888391) in the role [Software](software)",
])
def test_lists_and_several_conditions_read_back(text):
    names = dict(NAMES, A5000000001="Bob", I136199984="Harvard")
    assert render_core(_parse(text), lambda v, c=None: names.get(str(v))) == text


class _PagedCtx:
    """A count, then `hits` handed out a page (the body's size) at a time."""

    def __init__(self, hits, seats_each=1):
        self.hits, self.seats_each, self.bodies = list(hits), seats_each, []

    def search(self, body, what, index=None):
        self.bodies.append(body)
        if body.get("size") == 0:
            return {"hits": {"total": {"value": len(self.hits)}},
                    "aggregations": {"seats": {"value": len(self.hits) * self.seats_each}}}
        start = 0 if "search_after" not in body else body["search_after"][0] + 1
        page = [dict(h, sort=[start + i]) for i, h in enumerate(self.hits[start:start + body["size"]])]
        return {"hits": {"hits": page}}


def _work(i, seats):
    return {"_source": {"id": f"https://openalex.org/W{i}", "authorships_full": seats}}


def test_scan_reads_every_page_and_reduces_each():
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    hits = [_work(i, [_seat(JANE, [SOFTWARE] if i % 2 else [])]) for i in range(7)]
    ctx = _PagedCtx(hits, seats_each=SA.PAGE_SEATS // 3)     # pages of 3 works
    assert SA.matching_works(ctx, node, None) == [f"https://openalex.org/W{i}" for i in (1, 3, 5)]
    assert [b["size"] for b in ctx.bodies[1:]] == [3, 3, 3]


def test_several_conditions_in_one_query_share_one_budget():
    from query_translation.analytics import AnalyticsError
    node = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    ctx = _PagedCtx([_work(i, [_seat(JANE)]) for i in range(10)])
    ctx.same_authorship_read = (SA.CANDIDATE_LIMIT - 5, 0)    # an earlier condition read most of it
    with pytest.raises(AnalyticsError) as e:
        SA.matching_works(ctx, node, None)
    assert e.value.code == "too_many_works_to_check"


def test_the_people_form_counts_each_person_once_a_work(monkeypatch):
    from query_translation import analytics as A
    from query_translation import walk_exec as WX
    monkeypatch.setattr(WX, "_works_query", lambda oqo, ctx: {"match_all": {}})
    monkeypatch.setattr(WX, "_count", lambda ctx, q, what: 42)
    monkeypatch.setattr(WX, "_name", lambda rows, ctx: None)
    other = "https://openalex.org/A9"
    hits = [_work(1, [_seat(JANE, lineage=[UBC]), _seat(JANE, lineage=[UBC]), _seat(other)]),
            _work(2, [_seat(JANE, lineage=[UBC]), _seat(other, lineage=[UBC])]),
            _work(3, [_seat(other, lineage=["https://openalex.org/I1"])])]
    ctx = _PagedCtx(hits)
    ctx.deadline = A.Deadline()
    oqo = _parse(CANONICAL[7])
    body = SA.split_by_authorship(oqo, ctx)
    assert [(r["key"], r["count"]) for r in body["group_by"]] == [(JANE, 2), (other, 1)]
    assert body["summary"]["all"]["count"] == 42 and body["meta"]["rows_count"] == 2


def test_top_level_conditions_narrow_each_other(monkeypatch):
    from query_translation import walk_exec as WX
    monkeypatch.setattr(WX, "_works_query", lambda oqo, ctx: None)
    a = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), LeafFilter(ROLE, "software")])
    b = AuthorshipFilter(filters=[LeafFilter(PERSON, "A5000000001"), LeafFilter(ROLE, "data-curation")])
    ctx = _PagedCtx([])
    SA.resolve_rows(OQO(get_rows="works", filter_rows=[a, b]), [a, b], ctx)
    first_count = ctx.bodies[0]["query"]
    assert str(SA.superset_query(b)) in str(first_count)


@pytest.mark.parametrize("oqo,why", [
    ({"get_rows": "works", "filter_rows": [{"join": "or", "is_negated": True, "filters": [
        {"same_authorship": [{"column_id": PERSON, "value": "A1"}, {"column_id": ROLE, "value": "software"}]},
        {"column_id": "type", "value": "article"}]}]}, "can't be negated"),
    ({"get_rows": "works", "filter_rows": [{"same_authorship": [
        {"column_id": PERSON, "value": "A1"}, {"column_id": PERSON, "value": "A2"}]}]}, "names one person"),
    ({"get_rows": "works", "group_by": [{"column_id": PERSON, "same_authorship": [
        {"column_id": PERSON, "value": "A1"}, {"column_id": ROLE, "value": "software"}]}]}, "names no person"),
    ({"get_rows": "works", "group_by": [{"column_id": "publication_year", "conditions": [
        {"same_authorship": [{"column_id": PERSON, "value": "A1"}, {"column_id": ROLE, "value": "software"}]}]}]},
     "own conditions"),
    ({"get_rows": "works", "group_by": [{"column_id": PERSON, "same_authorship": [
        {"column_id": ROLE, "value": "software"}]}], "calculate": [{"measure": "count"}, {"measure": "count"}]},
     "counts works"),
])
def test_validation_refuses_what_would_fail_at_run_time(oqo, why):
    errors = validate_oqo(OQO.from_dict(oqo)).errors
    assert any(why in e.message for e in errors), [e.message for e in errors]


def test_full_url_values_validate_before_canonicalizing():
    oqo = OQO.from_dict({"get_rows": "works", "filter_rows": [{"same_authorship": [
        {"column_id": PERSON, "value": "https://openalex.org/A5023888391"},
        {"column_id": ROLE, "value": "https://openalex.org/contributor-roles/software"}]}]})
    assert validate_oqo(oqo).errors == []


# --- `in any role` and `in any of the roles` (23 Nov) -------------------------------
ANY_ROLE_TEXTS = [
    "get works with [Jane Smith](A5023888391) in any role",
    "get works with [Jane Smith](A5023888391) in the role [Data curation](data-curation) or "
    "[Software](software)",
    "get works with [Jane Smith](A5023888391) in the role [Data curation](data-curation), "
    "[Methodology](methodology), or [Software](software)",
    "get the count of works about kelp by author in any role",
    "get the count of works about kelp by author listing [UBC](I141945490) on the work in the role "
    "[Editor](editor) or [Software](software)",
    "get works with an author in any role",
]


@pytest.mark.parametrize("text", ANY_ROLE_TEXTS)
def test_any_role_reads_back(text):
    assert render_core(_parse(text), _resolver) == text
    assert validate_oqo(_parse(text)).errors == []


def test_any_role_is_the_has_a_value_form():
    from query_translation.oqo import any_role
    oqo = _parse(ANY_ROLE_TEXTS[0])
    assert oqo.filter_rows == [AuthorshipFilter(filters=[LeafFilter(PERSON, "A5023888391"), any_role()])]
    assert oqo.to_dict()["filter_rows"][0]["same_authorship"][1] == {
        "column_id": ROLE, "value": None, "is_negated": True}


def test_any_role_needs_a_role_on_that_persons_own_place():
    node = _parse(ANY_ROLE_TEXTS[0]).filter_rows[0]
    match = SA.matcher(node)
    assert match(_seat(JANE, [SOFTWARE]))
    assert not match(_seat(JANE)) and not match(_seat("https://openalex.org/A9", [SOFTWARE]))
    assert SA.superset_query(node)["bool"]["filter"][1] == {"exists": {"field": "authorships_full.contributor_roles.id"}}


def test_any_of_the_roles_takes_either():
    node = _parse(ANY_ROLE_TEXTS[1]).filter_rows[0]
    match = SA.matcher(node)
    curation = "https://openalex.org/contributor-roles/data-curation"
    assert match(_seat(JANE, [SOFTWARE])) and match(_seat(JANE, [curation]))
    assert not match(_seat(JANE, ["https://openalex.org/contributor-roles/methodology"]))
    assert SA.superset_query(node)["bool"]["filter"][1] == {
        "terms": {"authorships_full.contributor_roles.id": [curation, SOFTWARE]}}


def test_a_role_alone_in_any_form_needs_no_check():
    assert not _parse(ANY_ROLE_TEXTS[5]).filter_rows[0].pairs


def test_in_any_of_the_roles_reads_as_the_role_or():
    a = _parse("get works with [Jane Smith](A5023888391) in any of the roles [Software](software) or "
               "[Data curation](data-curation)")
    assert a.to_dict() == _parse(ANY_ROLE_TEXTS[1]).to_dict()


def test_the_lists_conjunction_decides_every_or_one():
    every = _parse("get works with [Jane Smith](A5023888391) in the roles [Software](software), "
                   "[Data curation](data-curation), and [Methodology](methodology)").filter_rows[0]
    one = _parse("get works with [Jane Smith](A5023888391) in the role [Software](software), "
                 "[Data curation](data-curation), or [Methodology](methodology)").filter_rows[0]
    assert len(every.filters) == 4 and len(one.filters) == 2
