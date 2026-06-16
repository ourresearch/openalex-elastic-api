"""Unit tests for the editor's cursor->grammar-state resolver (oxjob #357).

Pure tests — no Flask/ES. Run with:
    cd ~/Documents/openalex-elastic-api
    PYTHONPATH=. .venv-oql/bin/python -m pytest tests/oql/test_parse_context.py -q --noconftest
"""
import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_context import parse_context, parse_context as pc  # noqa: E402
from query_translation import oql_context as C  # noqa: E402
from query_translation.oql_lang import lex, _Parser, _ALIAS  # noqa: E402


def cat(q, pos=None):
    return parse_context(q, pos)["context"]["category"]


def ctx(q, pos=None):
    return parse_context(q, pos)["context"]


# --- the state table ----------------------------------------------------------
# Each row: (oql, cursor_pos_or_None, expected_category, extra_assertions_dict)
TABLE = [
    # entity slot
    ("", None, C.ENTITY, {}),
    ("wor", None, C.ENTITY, {"prefix": "wor"}),
    ("works", None, C.ENTITY, {"prefix": "works"}),
    # after a complete entity -> directives / where / end
    ("works ", None, C.DIRECTIVE, {}),
    ("works", 5, C.ENTITY, {}),            # cursor at end of the word = still typing it
    # field slot
    ("works where ", None, C.FIELD, {}),
    ("works where ye", None, C.FIELD, {"prefix": "ye"}),
    ("works where year > 2000 and ", None, C.FIELD, {}),
    # operator slot
    ("works where year", None, C.FIELD, {"prefix": "year"}),  # still typing field
    ("works where year ", None, C.OPERATOR, {"field": "year", "value_kind": "num"}),
    ("works where institution ", None, C.OPERATOR, {"field": "institution",
                                                    "value_kind": "id"}),
    ("works where title ", None, C.OPERATOR, {"field": "title", "value_kind": "search"}),
    # value slot — the headline acceptance case
    ("works where institution is har", None, C.VALUE,
     {"value_kind": "id", "autocomplete_entity": "institutions", "prefix": "har",
      "field": "institution"}),
    ("works where institution is ", None, C.VALUE,
     {"value_kind": "id", "autocomplete_entity": "institutions"}),
    ("works where author is ", None, C.VALUE, {"autocomplete_entity": "authors"}),
    ("works where source is ", None, C.VALUE, {"autocomplete_entity": "sources"}),
    ("works where funder is ", None, C.VALUE, {"autocomplete_entity": "funders"}),
    ("works where SDG is ", None, C.VALUE, {"autocomplete_entity": "sdgs"}),
    ("works where year > ", None, C.VALUE, {"value_kind": "num"}),
    ("works where type is ", None, C.VALUE, {"value_kind": "enum"}),
    # multi-word operator: `is not` keeps us in VALUE
    ("works where institution is not ", None, C.VALUE, {"value_kind": "id"}),
    # parens-bag value groups (#363): inside `is (…)` the cursor is a VALUE slot
    ("works where institution is (", None, C.VALUE, {"in_list": True}),
    ("works where type is (article or ", None, C.VALUE, {"in_list": True,
                                                         "value_kind": "enum"}),
    # after a complete clause -> connective
    ("works where year > 2000 ", None, C.CONNECTIVE, {}),
    ("works where institution is I27837315 ", None, C.CONNECTIVE, {}),
    # boolean "it's ..." clause
    ("works where it's ", None, C.VALUE, {"value_kind": "bool"}),
    # connective then new field
    ("works where year > 2000 and ti", None, C.FIELD, {"prefix": "ti"}),
    # Under the parens-bag grammar (#363) `title has foo` is a complete
    # single-term clause (a bare 2+ term list is illegal), so `and (` opens a new
    # *clause* group -> the cursor expects a FIELD, not another search term.
    ("works where title has foo and (", None, C.FIELD, {}),
    # a search-term group continues the SEARCH: inside `has (` a term slot
    ("works where title has (foo or ", None, C.VALUE,
     {"value_kind": "search", "field": "title"}),
    # directives
    ("works sort by ", None, C.FIELD, {}),
    ("works group by ", None, C.FIELD, {}),
    # suppression: inside a string / annotation
    ('works where title has "clim', None, C.NONE, {}),   # unterminated string
    ('works where institution is I27 [Harv', None, C.NONE, {}),  # unterminated annot
    ('works where title has "climate"', 27, C.NONE, {}),  # strictly inside string
]


def test_state_table():
    failures = []
    for oql, pos, expected_cat, extra in TABLE:
        c = ctx(oql, pos)
        if c["category"] != expected_cat:
            failures.append(f"{oql!r}@{pos}: category {c['category']!r} != {expected_cat!r}")
            continue
        for k, v in extra.items():
            if c.get(k) != v:
                failures.append(f"{oql!r}@{pos}: {k}={c.get(k)!r} != {v!r}")
    assert not failures, "\n".join(failures)


def test_entity_resolved():
    assert parse_context("works where institution is har")["entity"] == "works"
    assert parse_context("authors sort by works_count")["entity"] == "authors"
    assert parse_context("wor")["entity"] is None  # not yet a complete entity


def test_replace_range_overwrites_partial_word():
    r = ctx("works where institution is har")
    # 'har' starts at offset 27
    assert r["replace_range"] == {"start": 27, "end": 30}
    assert r["prefix"] == "har"


def test_replace_range_empty_in_whitespace():
    r = ctx("works where institution is ")
    assert r["replace_range"] == {"start": 27, "end": 27}
    assert r["prefix"] == ""


def test_multiword_field_prefix_extends():
    # `last known inst` is a prefix of the alias "last known institution"
    r = ctx("works where last known inst")
    assert r["category"] == C.FIELD
    assert "last known inst" in r["prefix"]


# --- multiword VALUE widening (oxjob #357 iter-3 bug 1) -----------------------
# A value being typed across several words (`university of florida`, `united
# kingdom`) must classify as VALUE with the WHOLE typed value as the prefix +
# replace_range — not just the last word — so the entity/enum search sees it all.
def test_multiword_id_value_prefix_extends():
    q = "works where institution is university of fl"
    r = ctx(q)
    assert r["category"] == C.VALUE
    assert r["value_kind"] == "id"
    assert r["autocomplete_entity"] == "institutions"
    assert r["prefix"] == "university of fl"
    # replace_range spans from the first value word to the cursor
    assert r["replace_range"]["start"] == q.index("university")
    assert r["replace_range"]["end"] == len(q)


def test_multiword_enum_value_prefix_extends():
    q = "works where country is united ki"
    r = ctx(q)
    assert r["category"] == C.VALUE
    assert r["value_kind"] == "enum"
    assert r["prefix"] == "united ki"
    assert r["replace_range"]["start"] == q.index("united")


def test_single_word_value_unaffected_by_widening():
    # the existing single-token value path must be untouched (no over-widening)
    r = ctx("works where institution is har")
    assert r["category"] == C.VALUE
    assert r["prefix"] == "har"
    assert r["replace_range"] == {"start": 27, "end": 30}


def test_post_connective_id_sibling_carries_autocomplete_entity():
    # after `institution is <id> and/or ▮` the sibling must carry autocomplete_entity
    # so the editor's "Another <field> value" section can do a live entity lookup
    # (multi-value id filters — #357 iter-3).
    for conn in ("and", "or"):
        r = ctx(f"works where institution is I27837315 [University of Michigan] {conn} ")
        assert r["category"] == C.FIELD
        assert r["after_connective"] == conn
        sib = r["sibling"]
        assert sib["field"] == "institution"
        assert sib["value_kind"] == "id"
        assert sib["autocomplete_entity"] == "institutions"
        assert sib["value_range"]  # for the auto-paren rewrite


def test_post_connective_multiword_id_value_widens():
    # typing a multi-word 2nd institution name after `and`/`or` (past the first word)
    # must classify as the after_connective FIELD+id-sibling context with the WHOLE
    # name as the prefix — not degrade to NONE (#357 iter-3 multi-value).
    q = ("works where institution is I27837315 [University of Michigan] "
         "and university of fl")
    r = ctx(q)
    assert r["category"] == C.FIELD
    assert r["after_connective"] == "and"
    assert r["sibling"]["value_kind"] == "id"
    assert r["sibling"]["autocomplete_entity"] == "institutions"
    assert r["prefix"] == "university of fl"
    assert r["replace_range"]["start"] == q.index("university of fl")


def test_post_connective_multiword_enum_value_widens():
    r = ctx("works where type is article or social sci")
    assert r["category"] == C.FIELD and r["after_connective"] == "or"
    assert r["sibling"]["value_kind"] == "enum"
    assert r["prefix"] == "social sci"


def test_post_connective_new_clause_not_swallowed_as_value():
    # a real new clause after the connective (its own field+operator) must classify as
    # that clause's VALUE — NOT get swallowed into one giant value prefix for the 1st.
    r = ctx("works where institution is I27837315 [University of Michigan] "
            "and last known institution is har")
    assert r["category"] == C.VALUE
    assert r.get("after_connective") is None  # inside the 2nd clause's value, not after `and`
    # it's the SECOND clause's own institution value (last known institution), not a
    # widened mega-prefix for the first clause
    assert r["value_kind"] == "id"
    assert r["field"] == "last known institution"
    assert r["prefix"] == "har"


def test_post_connective_partial_multiword_field_stays_field():
    # a partial multi-word FIELD after the connective keeps the field interpretation
    # (its prefix widens as a field), not swallowed as a value run.
    r = ctx("works where institution is I27837315 [University of Michigan] "
            "and last known inst")
    assert r["category"] == C.FIELD
    assert r["prefix"] == "last known inst"


def test_post_connective_enum_sibling_has_no_autocomplete_entity():
    # enum siblings resolve from static config vocab, not a live /autocomplete route
    r = ctx("works where type is article or ")
    sib = r["sibling"]
    assert sib["value_kind"] == "enum"
    assert sib.get("autocomplete_entity") is None


def test_multiword_value_widening_with_resolved_prior_clause():
    # a prior clause already resolved to an id (`Ixxxx [Name]`) doesn't block the
    # widening of a later multiword value at the cursor (the realistic editor flow)
    q = ("works where institution is I27837315 [University of Michigan] "
         "and country is united k")
    r = ctx(q)
    assert r["category"] == C.VALUE
    assert r["value_kind"] == "enum"
    assert r["prefix"] == "united k"


def test_pos_out_of_range_is_clamped():
    assert cat("works where ", 9999) == C.FIELD
    assert cat("works", -5) == C.ENTITY


def test_never_raises_on_arbitrary_prefixes():
    # Typing a real query one char at a time must never throw.
    full = 'works where institution is I27837315 [Harvard] and title has "climate change" and year >= 2020 sort by citations desc'
    for i in range(len(full) + 1):
        parse_context(full, i)  # must not raise


# --- dual-mode resilience: the editor surface must survive EVERY prefix of a
#     diverse set of valid queries, always returning a known category (oxjob #363,
#     decision 15). This is the "a keystroke-in-progress never blanks the doc"
#     guarantee — and it exercises the context parser across value lists, the search
#     sub-grammar, proximity, collections, directives, and nested parens. ---
_VALID_CATEGORIES = {C.ENTITY, C.FIELD, C.OPERATOR, C.VALUE, C.CONNECTIVE,
                     C.DIRECTIVE, C.END, C.NONE}

_FUZZ_QUERIES = [
    "works where type is (article or review)",
    "works where institution is in collection col_abc123",
    "works where abstract is similar to \"machine learning\"",
    'works where title has "smart phone" within 3 words',
    "works where (year >= 2020 and is_oa is true) or type is review",
    "works where it's open access and it has a DOI",
    "authors where works_count > 100 sort by cited_by_count desc",
    "works group by type sample 50",
    "works where title has foo and (climate or warming)",
]


def test_context_never_raises_and_always_classifies():
    failures = []
    for q in _FUZZ_QUERIES:
        for i in range(len(q) + 1):
            try:
                r = parse_context(q, i)
            except Exception as e:  # noqa: BLE001 — any throw is a hard failure
                failures.append(f"{q!r}@{i}: raised {e!r}")
                continue
            cat = r["context"]["category"]
            if cat not in _VALID_CATEGORIES:
                failures.append(f"{q!r}@{i}: unknown category {cat!r}")
    assert not failures, "\n".join(failures[:20])


def test_categories_are_the_engine_constants():
    # Single source of grammar truth: the editor's category strings ARE the parser's.
    from query_translation import oql_lang as L
    assert (C.ENTITY, C.FIELD, C.OPERATOR, C.VALUE, C.CONNECTIVE,
            C.DIRECTIVE, C.END, C.NONE) == (
        L.CTX_ENTITY, L.CTX_FIELD, L.CTX_OPERATOR, L.CTX_VALUE, L.CTX_CONNECTIVE,
        L.CTX_DIRECTIVE, L.CTX_END, L.CTX_NONE)


def test_context_mode_does_not_perturb_strict_parse():
    # A context-mode parse must not corrupt a subsequent strict parse of the same
    # tokens (the _ctx_mode flag / partial state stays contained).
    from query_translation.oql_lang import parse
    q = "works where year >= 2020 and type is review"
    parse_context(q, 12)          # context-mode run over a prefix
    oqo = parse(q)                # strict parse must still succeed + be correct
    assert oqo.get_rows == "works"
    assert len(oqo.filter_rows) == 2


# --- post-connective sectioned-menu context (oxjob #357) ------------------------
# After `<value> or ▮` / `<value> and ▮` the cursor is a FIELD slot (a new clause may
# start) AND it carries the "sibling" clause so the editor can offer "add another value
# to this filter" (auto-paren rewrite). Before the fix this returned NONE for `is`-value
# clauses (the value-arity guard fired on the dangling connective).
def test_post_connective_is_value_is_field_not_none():
    for conn in ("or", "and"):
        c = ctx(f"works where type is article {conn} ")
        assert c["category"] == C.FIELD, f"{conn}: {c['category']}"
        assert c["after_connective"] == conn
        # still offers the normal field list for the "new filter" section
        assert any(s["kind"] == "field" for s in c["suggestions"])


def test_connective_menu_offers_directives_too():
    # "menu 1" of the two-level design: after a complete clause, offer and/or AND the
    # trailing directives (sort by / group by / sample) — but never re-offer `where`.
    c = ctx("works where year > 2000 ")
    assert c["category"] == C.CONNECTIVE
    vals = {s["value"] for s in c["suggestions"]}
    assert {"and", "or", "sort by", "group by", "sample"} <= vals
    assert "where" not in vals


def test_post_connective_carries_enum_sibling_with_ranges():
    q = "works where type is article or "
    c = ctx(q)
    sib = c["sibling"]
    assert sib["field"] == "type" and sib["value_kind"] == "enum"
    assert sib["column"] == "type"
    # clause_range spans "type is article"; value_range spans just "article"
    assert q[sib["clause_range"]["start"]:sib["clause_range"]["end"]] == "type is article"
    assert q[sib["value_range"]["start"]:sib["value_range"]["end"]] == "article"


def test_post_connective_paren_sibling_value_range_covers_list():
    q = "works where type is (article or book) or "
    sib = ctx(q)["sibling"]
    assert q[sib["value_range"]["start"]:sib["value_range"]["end"]] == "(article or book)"


def test_post_connective_no_sibling_for_bool_clause():
    # `it's open access` has no enum value list to extend -> FIELD, but no sibling.
    c = ctx("works where it's open access or ")
    assert c["category"] == C.FIELD
    assert c["after_connective"] == "or"
    assert "sibling" not in c


def test_post_connective_typing_field_prefix_still_field():
    # once the user types a field name after the connective it's plain field-completion
    c = ctx("works where type is article or insti")
    assert c["category"] == C.FIELD
    assert c["prefix"] == "insti"


def test_collection_value_slot_is_recognized():
    # `is in collection ` lands in a value slot (the col_ id) — the editor must not
    # blank here just because it's the newest operator.
    c = ctx("works where work is in collection ")
    assert c["category"] == C.VALUE


def test_semantic_value_slot():
    c = ctx("works where abstract is similar to ")
    assert c["category"] == C.VALUE
    assert c["value_kind"] == "search"


# --- parser-agreement: the walker's field/operator recognition must match the
#     production _Parser on well-formed inputs (guards drift from the frozen engine) ---
def test_field_matcher_agrees_with_parser():
    fields_to_check = ["year", "institution", "title", "title & abstract",
                       "last known institution", "open access", "type", "DOI"]
    for spelling in fields_to_check:
        toks = lex(f"{spelling} is x") if spelling not in ("title", "title & abstract", "open access") else lex(f"{spelling} has x")
        m = C._match_field(toks, 0)
        assert m is not None, f"walker failed to match field {spelling!r}"
        _sp, fld, flen = m
        # the parser's greedy matcher consumes the same field
        p = _Parser(toks)
        pspelling, pfld = p._parse_field()
        assert fld.column == pfld.column, f"{spelling!r}: walker {fld.column} != parser {pfld.column}"


def test_operator_matcher_agrees_with_parser():
    cases = [("year is", "is"), ("year is not", "isnot"),
             ("institution is any of", "in"), ("institution is not any of", "nin"),
             ("institution is in", "in"), ("year >=", ">="),
             ("title has", "has")]
    for text, expected_op in cases:
        toks = lex(text + " x") if not text.endswith("of") else lex(text + " (x)")
        # skip the field
        m = C._match_field(toks, 0)
        _sp, _fld, flen = m
        op = C._match_operator(toks, flen)
        assert op is not None and op[2], f"{text!r}: walker op incomplete: {op}"
        assert op[0] == expected_op, f"{text!r}: walker {op[0]} != {expected_op}"


def test_editor_matchers_are_the_shared_engine_matchers():
    # oxjob #363: the editor no longer keeps a parallel reimplementation — its
    # matchers ARE the production engine's, so they cannot drift.
    from query_translation.oql_lang import match_field, match_operator
    assert C._match_field is match_field
    assert C._match_operator is match_operator


def test_editor_recognizes_is_in_collection_operator():
    # The old parallel walker missed `is [not] in collection` entirely (it had no
    # collection branch); sharing the engine matcher fixes that latent drift.
    toks = lex("work is in collection col_abc")
    flen = C._match_field(toks, 0)[2]
    op = C._match_operator(toks, flen)
    assert op is not None and op[0] == "incoll" and op[2]  # complete
    toks2 = lex("work is not in collection col_abc")
    flen2 = C._match_field(toks2, 0)[2]
    op2 = C._match_operator(toks2, flen2)
    assert op2 is not None and op2[0] == "nincoll" and op2[2]


# --- iter-5: click-anywhere gaps (oxjob #357) ----------------------------------
_SORT_Q = "works where institution is I27837315 [UM] sort by citation count desc"


def test_direction_click_offers_asc_desc():
    # cursor inside `desc` -> the slot IS the asc/desc choice
    pos = _SORT_Q.index("desc") + 2
    c = ctx(_SORT_Q, pos)
    assert c["category"] == "direction"
    assert [s["value"] for s in c["suggestions"]] == ["asc", "desc"]
    assert all(s["kind"] == "direction" for s in c["suggestions"])
    assert c["replace_range"] == {"start": _SORT_Q.index("desc"),
                                  "end": _SORT_Q.index("desc") + 4}


def test_open_slot_after_sort_column_offers_direction_too():
    q = "works sort by year "
    c = ctx(q)
    vals = [s["value"] for s in c["suggestions"]]
    assert vals[:2] == ["asc", "desc"]          # direction first
    assert "group by" in vals                    # the END directives still offered


def test_direction_not_offered_after_group_by():
    q = "works group by type "
    c = ctx(q)
    vals = [s["value"] for s in c["suggestions"]]
    assert "asc" not in vals and "desc" not in vals


def test_direction_not_offered_when_direction_already_present():
    q = "works sort by year desc "
    c = ctx(q)
    vals = [s["value"] for s in c["suggestions"]]
    assert "asc" not in vals and "desc" not in vals


def test_direction_multi_sort_second_segment():
    # after a comma the new segment gets its own direction slot
    q = "works sort by year desc, citation count "
    c = ctx(q)
    vals = [s["value"] for s in c["suggestions"]]
    assert vals[:2] == ["asc", "desc"]


def test_annotation_click_reanchors_to_the_value():
    # cursor inside `[UM]` -> the id-value context of the preceding token
    q = "works where institution is I27837315 [UM] sort by year"
    pos = q.index("[UM]") + 2
    c = ctx(q, pos)
    assert c["category"] == C.VALUE
    assert c["value_kind"] == "id"
    assert c["autocomplete_entity"] == "institutions"
    assert c["prefix"] == "I27837315"
    assert c["replace_range"] == {"start": q.index("I27837315"),
                                  "end": q.index("I27837315") + len("I27837315")}


def test_annotation_click_with_no_preceding_word_stays_suppressed():
    q = 'works where title has "x" [note]'
    pos = q.index("[note]") + 2  # preceding token is a STRING, not a WORD
    assert cat(q, pos) == C.NONE


def test_string_click_still_suppressed():
    q = 'works where title has "climate change"'
    pos = q.index("climate") + 3
    assert cat(q, pos) == C.NONE


def test_direction_click_after_enum_value_clause():
    # regression (#357 iter-5): with an enum clause before the sort, the multiword-
    # value widener used to swallow `article sort by citation count` as one value
    # run, so the cursor in `desc` never reached the direction slot.
    q = "works where type is article sort by citation count desc"
    pos = q.index("desc") + 2
    c = ctx(q, pos)
    assert c["category"] == "direction"
    assert [s["value"] for s in c["suggestions"]] == ["asc", "desc"]


def test_multiword_value_widening_still_works():
    # the directive-boundary stop must not break the original iter-3 widening
    c = ctx("works where institution is university of fl")
    assert c["category"] == C.VALUE
    assert c["prefix"] == "university of fl"
