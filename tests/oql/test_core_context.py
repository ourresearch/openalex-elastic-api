"""Editor autocomplete for OQL core v3 (oxjob #1597): `/parse-context` on get-only statements.

Pure tests, no Flask app, ES or DB (one route test builds a bare Flask app). A `|` in a
case marks the cursor. Run:
    PYTHONPATH=. pytest tests/oql/test_core_context.py -q --noconftest
"""
import json
import os

import pytest

import tests.oql._qt_loader  # noqa: F401

from query_translation import oql_core as C  # noqa: E402
from query_translation import oql_core_context as X  # noqa: E402
from query_translation.oql_context import _parse_context_old, parse_context  # noqa: E402
from query_translation.oql_core import parse_core  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "core_v3_cases.json")))
CASES = [c["new"] for c in DATA["cases"]]

# the #1744 demo questions (nl-search-page/work/demo_questions.md), in today's core form
DEMO = [
    "get the count and percent retracted of works in [Journal of Healthcare Engineering](S36625193) by year",
    'get the count of works about "large language models" by year since 2018',
    'get the count of works since 2022 about "quantum computing" by country',
    "get the count of retracted works from 2023 by journal",
    'get the count and mean FWCI of works since 2015 about "perovskite solar cells" by country, '
    "highest mean FWCI first",
    "get the count and mean FWCI of works since 2015 by institution in ([Indian Institute of Technology "
    "Bombay](I162827531), [Indian Institute of Technology Delhi](I68891433), [Indian Institute of Science "
    "Bangalore](I59270414))",
    "get the count of works since 2019 about (microplastics AND marine) by author. Show h-index.",
    "get the count of [University of Cape Town](I157614274)'s works since 2015 by SDG",
    "get [Jennifer A. Doudna](A5067184382)'s works from 2011–2013 about (programmable AND RNA AND Cas9 AND "
    "endonuclease) in [Science](S3880285)",
    "get works about CRISPR where citation count is at least 1000, most cited first",
    "get works about (coral reefs) from [Massachusetts Institute of Technology](I63966007) since 2020, "
    "most cited first",
    "get institutions in [Brazil](BR)",
    "get the count and share of [France](FR)'s works by year from 2013–2025 and open access status",
    "get the count of works from both [University of Oxford](I40120149) and [University of Cambridge]"
    "(I241749) by year since 2015",
    "get [University of Oxford](I40120149)'s works about (malaria AND vaccine), newest first",
    "get the count of works from [Kenya](KE) by country except [Kenya](KE)",
]


def at(text):
    """parse_context with the cursor where `|` is."""
    pos = text.index("|") if "|" in text else None
    return parse_context(text.replace("|", ""), pos)


def ctx(text):
    return at(text)["context"]


def values(c):
    return [s["value"] for s in c["suggestions"]]


# ---------------------------------------------------------------------------
# Cursor cases: (text with |, slot, prefix, must-include values, must-exclude, entities)
# ---------------------------------------------------------------------------
CURSOR_CASES = [
    ("g|", "head", "g", ["get"], [], []),
    ("get |", "head", "", ["the", "works", "articles", "open access", "authors", "journals"], ["where"],
     ["institutions", "countries", "authors"]),
    ("get ar|", "head", "ar", ["articles"], ["works"], ["institutions", "countries", "authors"]),
    ("get the |", "measure", "", ["count", "share", "mean FWCI", "sum of citations", "percent open access"],
     ["h-index"], []),
    ("get the mean |", "measure", "mean ", ["mean FWCI", "mean citations"], ["count"], []),
    ("get the count |", "measure", "", ["and", "of"], [], []),
    ("get the sum of citations |", "measure", "", ["and", "to", "of"], [], []),
    ("get the count of |", "noun", "", ["all works", "works", "articles", "open access"], [],
     ["institutions", "countries", "authors"]),
    ("get the count of works |", "works-slot", "", ["about", "since", "from", "by", "in", "funded by", "where"],
     ["most cited first"], []),
    ("get works about (coral reefs) |", "works-slot", "", ["from", "since", "by", "in", "most cited first"],
     ["group by", "sample", "best matches first"], []),
    ("get works about (coral reefs) from [Massachusetts Institute of Technology](I63966007) since 2020 |",
     "works-slot", "", ["in", "funded by", "most cited first", C.AGE_ADJUSTED_WORDS], [], []),
    ("get works from |", "entity", "", ["both", "all of", "the collection", "2020"], [],
     ["institutions", "countries", "continents"]),
    ("get works from [Stan|", "entity", "[Stan", [], [], ["institutions", "countries", "continents"]),
    ("get works from Stanford Uni|", "entity", "Stanford Uni", [], [], ["institutions", "countries", "continents"]),
    ("get works from [Kenya](KE) |", "works-slot", "", ["or", "about", "since"], [], []),
    ("get works by |", "entity", "", [], [], ["authors"]),
    ("get works in |", "entity", "", ["the topic", "the field", "SDG", "the collection"], [], ["sources"]),
    ("get works in the t|", "entity", "the t", ["the topic"], ["the field"], ["sources"]),
    ("get works in the topic |", "entity", "", [], [], ["topics"]),
    ("get works in the subfield |", "entity", "", [], [], ["subfields"]),
    ("get works in the field |", "entity", "", [], [], ["fields"]),
    ("get works in the domain |", "entity", "", [], [], ["domains"]),
    ("get works in SDG |", "entity", "", [], [], ["sdgs"]),
    ("get works published by |", "entity", "", [], [], ["publishers"]),
    ("get works funded by |", "entity", "", [], [], ["funders"]),
    ("get works funded b|", "works-slot", "funded b", ["funded by"], ["about"], []),
    ("get works citing |", "entity", "", ["works in the collection"], [], ["works"]),
    ("get works co-authored with |", "entity", "", [], [], ["institutions"]),
    ("get works co-authored by |", "entity", "", [], [], ["authors"]),
    ("get works co-authored by [Jennifer A. Doudna](A5067184382) |", "works-slot", "", ["and"], [], []),
    ("get works under the |", "entity", "", [], [], ["licenses"]),
    ("get works under the [CC BY](cc-by) |", "works-slot", "", ["license"], [], []),
    ("get works with |", "search-text", "", [], [], []),
    ("get works with (kelp) |", "place", "", ["in the title", "in the abstract", "in the full text"], [], []),
    ("get works with (kelp) in the t|", "place", "in the t", ["in the title", "in the title or abstract"],
     ["in the abstract"], []),
    ("get works about kelp since |", "year", "", ["2025", "2020", "2015"], [], []),
    ("get works about kelp before 20|", "year", "20", ["2015"], [], []),
    ("get works about kelp, |", "order", "", ["most cited first", "newest first", C.AGE_ADJUSTED_WORDS],
     ["fewest works first"], []),
    ("get works about kelp, most c|", "order", "most c", ["most cited first", C.AGE_ADJUSTED_WORDS],
     ["newest first"], []),
    ("get [University of Kansas](I146416000)'s |", "noun", "", ["works", "articles", "open access"], ["the"], []),
    ("get [MIT](I63966007) |", "noun", "", ["'s"], [], []),
    ("get the count of works about kelp by |", "split", "", ["year", "country", "author", "institution", "SDG"],
     ["about"], []),
    ("get the count of works about kelp by coun|", "split", "coun", ["country"], ["year"], []),
    ("get the count of works about kelp by [Dou|", "split", "[Dou", [], [], ["authors"]),
    ("get the count of works about kelp by country |", "split", "",
     ["and", "in (…)", "except", "most works first", "fewest works first", "Show", "Only"], ["at"], []),
    ("get the count of works about kelp by author |", "split", "",
     ["and", "at", "with an h-index above", "where", "highest h-index first", "Show", "Only"], [], []),
    ("get the count of works by year |", "split", "", ["and", "since", "newest first", "most works first"], [], []),
    ("get the count of works by year since 2004 and |", "split", "", ["country", "type"], [], []),
    ("get the count and mean FWCI of works about kelp by country, |", "order", "",
     ["most works first", "highest mean FWCI first", "lowest mean FWCI first", "fewest works first",
      "alphabetical by country"],
     ["most cited first", "newest first"], []),
    ("get the mean FWCI of works about kelp by country, |", "order", "", ["highest first", "lowest first"],
     ["highest mean FWCI first"], []),
    ("get the count of works by country in (|", "entity", "", [], [], ["countries"]),
    ("get the count of works by country in ([United States](US), [Ch|", "entity", "[Ch", [], [], ["countries"]),
    ("get the count of works by SDG in (|", "entity", "", [], [], ["sdgs"]),
    ("get authors |", "things-slot", "", ["at", "in", "except", "with an h-index above", "where",
                                          "highest h-index first"], ["about"], []),
    ("get authors at |", "entity", "", [], [], ["institutions"]),
    ("get authors at [University of British Columbia](I141945490) |", "things-slot", "",
     ["since", "in 2+ years", "with an h-index above", "highest h-index first"], [], []),
    ("get institutions in |", "entity", "", [], [], ["countries", "continents"]),
    ("get institutions in [Brazil](BR), |", "order", "", ["most cited first", "highest h-index first"], [], []),
    ("get topics in |", "entity", "", ["the subfield", "the field", "the domain"], [], ["countries", "continents"]),
    ("get the count of works about kelp by author. |", "sentence", "", ["Show", "Only"], [], []),
    ("get the count of works about kelp by author. Show |", "measure", "", ["h-index", "works count", "mean FWCI"],
     [], []),
    ("get the count of works about kelp by author. Only |", "noun", "", ["authors"], ["institutions"], []),
    ("get the count of works about kelp by author. Only authors |", "things-slot", "",
     ["with at least", "with more than"], [], []),
    ("get the count of works about kelp by author. Only authors with at least 5 |", "noun", "",
     ["works about kelp", "works"], [], []),
    ("get the count of works where language is [English](en) by cou|", "split", "cou", ["country"], [], []),
]


@pytest.mark.parametrize("text,slot,prefix,has,hasnt,ents", CURSOR_CASES, ids=[c[0] for c in CURSOR_CASES])
def test_cursor_case(text, slot, prefix, has, hasnt, ents):
    c = ctx(text)
    assert c["category"] == "core", c
    assert c["slot"] == slot
    assert c["prefix"] == prefix
    vals = values(c)
    assert not [h for h in has if h not in vals], vals
    assert not [h for h in hasnt if h in vals], vals
    assert c["autocomplete_entities"] == ents
    # the range ends at the cursor or the end of the word under it, and starts at the prefix
    pos = text.index("|")
    rr = c["replace_range"]
    assert rr["start"] <= pos <= rr["end"]
    assert pos - rr["start"] == len(text[rr["start"]:pos])


def test_table_orders_start_with_the_default():
    assert values(ctx("get the count of works about kelp by country, |"))[0] == "most works first"
    assert values(ctx("get the count of works by year, |"))[:2] == ["oldest first", "newest first"]


def test_live_bug_no_more_where_group_by_sample():
    # live 2026-10-20: `get works about (coral reefs) ` suggested `where / group by / sample`
    vals = values(ctx("get works about (coral reefs) |"))
    assert "group by" not in vals and "sample" not in vals
    assert vals[:4] == ["about", "since", "from", "by"]


def test_replace_range_spans_words_already_typed():
    c = ctx("get works funded b|")
    assert c["replace_range"] == {"start": 10, "end": 18}
    c = ctx("get works from [Stan|")
    assert c["replace_range"] == {"start": 15, "end": 20}
    c = ctx("get works from [Stan|ford University")       # mid-word: replace to the word's end
    assert c["prefix"] == "[Stan" and c["replace_range"] == {"start": 15, "end": 24}   # `[Stanford`


def test_inserts_carry_their_caret():
    sug = {s["value"]: s for s in ctx("get works |")["suggestions"]}
    assert sug["about"]["insert"] == "about ()" and sug["about"]["insert"][sug["about"]["cursor"]] == ")"
    w = sug["with … in the title"]
    assert w["insert"] == "with () in the title" and w["insert"][w["cursor"]] == ")"
    orders = {s["value"]: s for s in ctx("get works about kelp |")["suggestions"]}
    assert orders["most cited first"]["insert"] == ", most cited first"


def test_inside_a_link_offers_a_swap_of_the_whole_link():
    q = "get works from [Stanford University](I97018004) since 2020"
    c = ctx(q[:20] + "|" + q[20:])
    link = "[Stanford University](I97018004)"
    assert c["slot"] == "link" and c["autocomplete_entities"] == ["institutions"]
    assert q[c["replace_range"]["start"]:c["replace_range"]["end"]] == link
    c = ctx("get the count of works by country in ([United St|ates](US), [China](CN))")
    assert c["slot"] == "link" and c["autocomplete_entities"] == ["countries"]
    c = ctx("get works in the field [Computer Sci|ence](17)")
    assert c["slot"] == "link" and c["autocomplete_entities"] == ["fields"]   # the slot names the kind


# ---------------------------------------------------------------------------
# A click on a written phrase of a choice slot: its alternatives, current first
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,phrase,slot,also", [
    ("get the co|unt of works by year", "count", "measure", "mean FWCI"),
    ("get the count and mean F|WCI of works by year", "mean FWCI", "measure", "count"),
    ("get works about kelp, most ci|ted first", "most cited first", "order", "newest first"),
    ("get the count of works about kelp by coun|try, fewest works first", "country", "split", "year"),
    ("get ar|ticles about kelp", "articles", "noun", "works"),
    ("get open ac|cess works", "open access", "adjective", "retracted"),
    ("get auth|ors at [UBC](I141945490)", "authors", "noun", "institutions"),
    ("get works since 20|15 about kelp", "2015", "year", "2025"),
    ("get the count of works by year, newest fi|rst", "newest first", "order", "oldest first"),
    ("get the count of works about kelp by author. Show h-ind|ex.", "h-index", "measure", "works count"),
])
def test_click_on_a_phrase_opens_its_alternatives(text, phrase, slot, also):
    c = ctx(text)
    q = text.replace("|", "")
    assert c["slot"] == slot and c["prefix"] == ""
    assert q[c["replace_range"]["start"]:c["replace_range"]["end"]] == phrase
    first = c["suggestions"][0]
    assert first["value"] == phrase and first["current"] is True
    assert also in values(c)
    assert sum(1 for s in c["suggestions"] if s.get("current")) == 1


def test_typing_at_the_end_is_not_a_click():
    c = ctx("get the count|")
    assert c["prefix"] == "count" and not any(s.get("current") for s in c["suggestions"])


# ---------------------------------------------------------------------------
# `where` tails: today's resolver, offsets shifted back
# ---------------------------------------------------------------------------
def test_where_tail_delegates_with_shifted_offsets():
    q = "get works about kelp where language is "
    r = parse_context(q)
    old = _parse_context_old("get works where language is ")
    assert r["context"]["category"] == old["context"]["category"] == "value"
    assert r["context"]["value_kind"] == old["context"]["value_kind"]
    assert r["context"]["suggestions"] == old["context"]["suggestions"]
    assert r["context"]["replace_range"] == {"start": len(q), "end": len(q)}
    q = "get works about kelp where ye"
    c = parse_context(q)["context"]
    assert c["category"] == "field" and c["prefix"] == "ye"
    assert q[c["replace_range"]["start"]:c["replace_range"]["end"]] == "ye"


def test_where_tail_in_a_table_and_after_a_split():
    c = ctx("get the count of works where language is [English](en) and ty| by country")
    assert c["category"] == "field" and c["prefix"] == "ty"
    c = ctx("get the count of works by author where |")
    assert c["category"] == "field"
    assert at("get the count of works by author where |")["entity"] == "authors"


def test_where_tail_drops_todays_directives():
    c = ctx("get works about kelp where language is [English](en) |")
    assert not [s for s in c.get("suggestions", []) if s.get("kind") == "directive"]


# ---------------------------------------------------------------------------
# Routing: today's grammar stays byte for byte
# ---------------------------------------------------------------------------
OLD = ["", "wor", "works", "works ", "works where ", "works where institution is har",
       "works where year > 2000 and ", "authors where works_count > 100",
       "get works where ", "get works where institution is har", "get authors where ",
       "get works where title has foo; then, ",
       "get authors at [UBC](I141945490) since 2022 who published works where ",
       "get institutions in [Africa](Q15) that published works where topic is [Malaria](T10091); then, ",
       "get works; then, group those works by year; finally, summarize using count",
       "get works sample 10", "get works group by type", "get authors group by ",
       "get funders that funded works where title has kelp"]


@pytest.mark.parametrize("q", OLD)
def test_old_grammar_unchanged(q):
    assert not X.is_core(q)
    for pos in sorted({0, len(q) // 2, len(q)}):
        assert parse_context(q, pos) == _parse_context_old(q, pos)


@pytest.mark.parametrize("q", ["g", "get", "get ", "get works about kelp", "get the count of works by year",
                               "Get articles since 2020", "get works about kelp where language is [English](en)",
                               "get authors at [UBC](I141945490)", "get [MIT](I63966007)'s works"])
def test_core_statements_route_to_core(q):
    assert X.is_core(q)


# ---------------------------------------------------------------------------
# One grammar: the walk reads every core sentence, and every offered phrase parses
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", CASES + DEMO)
def test_the_walk_reads_every_core_sentence_whole(q):
    parse_core(q)
    toks = X._tokens(q)
    w, stop = X._walk(q, toks, len(toks))
    assert isinstance(stop, X._Stop) and w.skipped == 0


@pytest.mark.parametrize("q", DEMO + CASES[:12])
def test_never_raises_at_any_cursor(q):
    for pos in range(len(q) + 1):
        r = X.core_context(q, pos)          # unwrapped: a crash here would be swallowed live
        assert r["context"]["category"] in ("core", "none") or r["context"].get("category")
        rr = r["context"].get("replace_range")
        if rr:
            assert 0 <= rr["start"] <= rr["end"] <= len(q)


@pytest.mark.parametrize("q", ["get [", "get the count of (", 'get works about "unclosed', "get works ,,, ..",
                               "get the the the", "get works from [A](I1) or or", "get the count of works by by",
                               "get works where (", "get ) (", "get authors. Only . Show"])
def test_malformed_input_never_raises(q):
    for pos in range(len(q) + 1):
        r = parse_context(q, pos)
        assert "context" in r


_LINK_FOR = {"from": "[Kenya](KE)", "by": "[Jennifer A. Doudna](A5067184382)", "in": "[Heliyon](S2898612692)",
             "funded by": "[Wellcome Trust](F4320311904)", "published by": "[Elsevier BV](P4310320990)",
             "co-authored with": "[Kiel University](I32021983)",
             "co-authored by": "[A](A5067184382) and [B](A5074743574)",
             "citing": "[X](W4399795944)", "in the topic": "[X](T10033)", "in the subfield": "[X](1702)",
             "in the field": "[X](17)", "in the domain": "[X](3)", "in SDG": "[X](13)",
             "in the collection": "[X](col_x)", "citing works in the collection": "[X](col_x)"}


def _fill(o):
    v = o["value"]
    if "insert" in o and "…" in v:
        ins = o["insert"]
        fill = "[CC BY](cc-by)" if "license" in v else "[A](A5067184382)" if "corresponding" in v else "(kelp)"
        return ins[:o["cursor"] - (1 if fill == "(kelp)" else 0)] + fill + ins[o["cursor"] + (1 if fill == "(kelp)" else 0):]
    if v == "about":
        return "about kelp"
    if v in ("since", "before", "through"):
        return v + " 2020"
    if v == "where":
        return "where language is [English](en)"
    return v + " " + _LINK_FOR[v]


def test_every_works_slot_phrase_parses():
    for ctx_text in ("get works ", "get the count of works "):
        for o in ctx(ctx_text + "|")["suggestions"]:
            if o["kind"] == "order" or (o["value"] == "by" and "the count" in ctx_text):
                continue
            parse_core(ctx_text + _fill(o) + (" by country" if "the count" in ctx_text else ""))


def test_every_slot_table_word_is_offered():
    # a new LINK_SLOTS or YEAR_OPS word is parsed by core and walked here; it must be offered too
    offered = set(values(ctx("get works |")))
    assert not [w for w in list(C.LINK_SLOTS) + list(C.YEAR_OPS) if w not in offered and w != "in"]


def test_author_record_words():
    q = "get authors ever in [Canada](CA)"
    parse_core(q)
    toks = X._tokens(q)
    w, _ = X._walk(q, toks, len(toks))
    assert w.skipped == 0


def test_every_number_split_and_order_parses():
    for m in ctx("get the |")["suggestions"]:
        parse_core(f"get the {m['value']} of works by country")
    for m in ctx("get the count of works by author. Show |")["suggestions"]:
        parse_core(f"get the count of works by author. Show {m['value']}.")
    for s in ctx("get the count of works by |")["suggestions"]:
        parse_core(f"get the count of works by {s['value']}")
    for o in ctx("get works about kelp, |")["suggestions"]:
        parse_core(f"get works about kelp, {o['value']}")
    for o in ctx("get authors, |")["suggestions"]:
        parse_core(f"get authors, {o['value']}")
    for base in ("get the count and mean FWCI of works by author", "get the mean FWCI of works by year",
                 "get the count of works by type"):
        for o in ctx(base + ", |")["suggestions"]:
            parse_core(f"{base}, {o['value']}")
    for o in ctx("get the count of works about kelp by author |")["suggestions"]:
        if o.get("insert", "").startswith(", "):
            parse_core("get the count of works about kelp by author" + o["insert"])


def test_every_noun_adjective_and_thing_parses():
    for o in ctx("get |")["suggestions"]:
        if o["kind"] == "adjective":
            parse_core(f"get {o['value']} works")
        elif o["kind"] == "noun":
            parse_core(f"get {o['value']}")
    for o in ctx("get authors |")["suggestions"]:
        if o["value"].startswith("with "):
            parse_core(f"get authors {o['value']} 50")
    for o in ctx("get the count of works about kelp by institution. Only institutions |")["suggestions"]:
        parse_core(f"get the count of works about kelp by institution. Only institutions {o['value']} 10 "
                   "works about kelp.")
    for o in ctx("get works with (kelp) |")["suggestions"]:
        parse_core(f"get works with (kelp) {o['value']}")
    for o in ctx("get works from |")["suggestions"]:
        if o["kind"] == "year":
            parse_core(f"get works from {o['value']}")
        elif o["value"] == "the collection":
            parse_core("get works from the collection [X](col_x)")
        else:
            parse_core(f"get works from {o['value']} [A](I40120149), [B](I241749), and [C](I1)"
                       if o["value"] == "all of" else "get works from both [A](I40120149) and [B](I241749)")


def test_sentence_inserts_parse():
    for o in ctx("get the count of works about kelp by author |")["suggestions"]:
        if o["kind"] == "sentence":
            tail = "h-index." if o["value"] == "Show" else "authors with at least 5 works about kelp."
            parse_core("get the count of works about kelp by author" + o["insert"] + tail)


# ---------------------------------------------------------------------------
# Help text and the vocabulary route
# ---------------------------------------------------------------------------
_PROBES = [c[0] for c in CURSOR_CASES]


def test_every_suggestion_has_short_help():
    for text in _PROBES:
        for s in ctx(text)["suggestions"]:
            assert s["detail"] and len(s["detail"]) <= 50, s
            assert s["doc"] and "—" not in s["doc"] and "—" not in s["detail"], s
            assert s["kind"] in ("keyword", "noun", "adjective", "measure", "split", "order", "place",
                                 "year", "sentence"), s


def test_vocabulary_covers_every_suggestion():
    vocab = {p["value"] for p in X.VOCABULARY}
    missing = set()
    for text in _PROBES:
        for s in ctx(text)["suggestions"]:
            if s["kind"] != "year" and s["value"] not in vocab and s["detail"] != "the same works as the table":
                missing.add(s["value"])
    assert not missing
    for p in X.VOCABULARY:
        assert set(p) == {"value", "kind", "detail", "doc"} and p["detail"] and p["doc"]
        assert len(p["detail"]) <= 50


def test_vocabulary_reads_cores_own_tables():
    vocab = {p["value"] for p in X.VOCABULARY}
    for words in (C.NOUN_TYPES, C.NOUN_THINGS, C.NOUN_THING_TYPES, C.DIM_COLUMNS, C.SINGULAR_THING,
                  C.ORDER_PHRASES, C.LINK_SLOTS, C.YEAR_OPS):
        assert not [w for w in words if w not in vocab and w != "in"], words
    assert set(C.ADJECTIVES.values()) | set(C.NEG_ADJECTIVES.values()) <= vocab
    assert {"in " + k for k in C.IN_KEYS.values()} <= vocab
    assert {"in " + p for p in C.SEARCH_FIELD_FOR} <= vocab


def test_vocabulary_route():
    from flask import Flask
    from query_translation.editor_views import blueprint
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    with app.test_client() as client:
        body = client.get("/oql-vocabulary").get_json()
        assert {"about", "funded by", "most cited first", "mean FWCI", "country"} <= {p["value"] for p in body["phrases"]}
        r = client.get("/parse-context", query_string={"q": "get works about (coral reefs) ", "pos": 30}).get_json()
        assert r["context"]["category"] == "core" and r["context"]["slot"] == "works-slot"


def test_latency_well_under_20ms():
    import time
    q = DEMO[4]
    t0 = time.perf_counter()
    for pos in range(len(q) + 1):
        parse_context(q, pos)
    per_call = (time.perf_counter() - t0) / (len(q) + 1)
    assert per_call < 0.005, per_call
