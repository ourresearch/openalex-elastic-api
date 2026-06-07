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
    # multi-word operator: `is not` / `is any of` keep us in VALUE
    ("works where institution is not ", None, C.VALUE, {"value_kind": "id"}),
    ("works where institution is any of (", None, C.VALUE, {"in_list": True}),
    ("works where type is any of (article, ", None, C.VALUE, {"in_list": True,
                                                              "value_kind": "enum"}),
    # mid multi-word operator (`is any` without `of`) -> OPERATOR (offer completion)
    ("works where institution is any ", None, C.OPERATOR, {}),
    # after a complete clause -> connective
    ("works where year > 2000 ", None, C.CONNECTIVE, {}),
    ("works where institution is I27837315 ", None, C.CONNECTIVE, {}),
    # boolean "it's ..." clause
    ("works where it's ", None, C.VALUE, {"value_kind": "bool"}),
    # connective then new field
    ("works where year > 2000 and ti", None, C.FIELD, {"prefix": "ti"}),
    # boolean group: '(' then field
    ("works where title contains foo and (", None, C.FIELD, {}),
    # directives
    ("works sort by ", None, C.FIELD, {}),
    ("works group by ", None, C.FIELD, {}),
    # suppression: inside a string / annotation
    ('works where title contains "clim', None, C.NONE, {}),   # unterminated string
    ('works where institution is I27 [Harv', None, C.NONE, {}),  # unterminated annot
    ('works where title contains "climate"', 33, C.NONE, {}),  # strictly inside string
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


def test_pos_out_of_range_is_clamped():
    assert cat("works where ", 9999) == C.FIELD
    assert cat("works", -5) == C.ENTITY


def test_never_raises_on_arbitrary_prefixes():
    # Typing a real query one char at a time must never throw.
    full = 'works where institution is I27837315 [Harvard] and title contains "climate change" and year >= 2020 sort by citations desc'
    for i in range(len(full) + 1):
        parse_context(full, i)  # must not raise


# --- parser-agreement: the walker's field/operator recognition must match the
#     production _Parser on well-formed inputs (guards drift from the frozen engine) ---
def test_field_matcher_agrees_with_parser():
    fields_to_check = ["year", "institution", "title", "title & abstract",
                       "last known institution", "open access", "type", "DOI"]
    for spelling in fields_to_check:
        toks = lex(f"{spelling} is x") if spelling not in ("title", "title & abstract", "open access") else lex(f"{spelling} contains x")
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
             ("title contains", "contains")]
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
