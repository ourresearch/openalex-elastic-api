"""
OQL v2 conformance harness — the normative round-trip test (oxjob #330).

For every row in docs/oql/corpus.yaml:
  * status ok / hint   -> parse(oql) equals the authored oqo (canonicalized),
                          AND OQO -> OQL -> OQO is the identity.
  * status error       -> parse(oql) raises OQLError whose .code == diagnostic.
  * status out-of-scope -> documented non-representable / intentionally
                           unsupported; not executed here.

Run:  .venv-oql/bin/python -m pytest tests/oql/test_corpus_roundtrip.py -q
"""
import os

import pytest
import yaml

from tests.oql.oql_v2 import parse, render, OQLError
from query_translation.oqo import OQO
from query_translation.oqo_canonicalizer import canonicalize_oqo

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "oql", "corpus.yaml")


def _load_rows():
    with open(CORPUS) as fh:
        data = yaml.safe_load(fh)
    return data["rows"]


ROWS = _load_rows()
OK_ROWS = [r for r in ROWS if r["status"] in ("ok", "hint")]
ERR_ROWS = [r for r in ROWS if r["status"] == "error"]


def _canon(oqo: OQO) -> dict:
    return canonicalize_oqo(oqo).to_dict()


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_oql_parses_to_authored_oqo(row):
    """The hand-authored OQL means exactly the authored OQO (independent oracle)."""
    if "oqo" not in row:
        pytest.skip("no explicit oqo oracle (round-trip-only row)")
    got = _canon(parse(row["oql"]))
    want = _canon(OQO.from_dict(row["oqo"]))
    assert got == want, f"{row['id']}: parse(oql) != authored oqo"


@pytest.mark.parametrize("row", OK_ROWS, ids=[r["id"] for r in OK_ROWS])
def test_roundtrip_identity(row):
    """OQO -> OQL -> OQO is the identity (the normative round-trip)."""
    # Start from the authored oqo when present, else from parse(oql).
    start = OQO.from_dict(row["oqo"]) if "oqo" in row else parse(row["oql"])
    start_c = canonicalize_oqo(start)
    rendered = render(start_c)
    back = canonicalize_oqo(parse(rendered))
    assert start_c.to_dict() == back.to_dict(), (
        f"{row['id']}: OQO->OQL->OQO not identity\n  OQL: {rendered}")


@pytest.mark.parametrize("row", ERR_ROWS, ids=[r["id"] for r in ERR_ROWS])
def test_error_cases_have_named_diagnostic(row):
    """Every ✗ case raises a loud, named diagnostic (never a silent/wrong result)."""
    with pytest.raises(OQLError) as exc:
        parse(row["oql"])
    assert exc.value.code == row["diagnostic"], (
        f"{row['id']}: expected {row['diagnostic']}, got {exc.value.code}")
    assert exc.value.fixit, f"{row['id']}: diagnostic must carry a fix-it"


def test_value_case_is_canonicalized():
    """Enum slugs -> lowercase; ISO country codes -> uppercase; IDs/col_ verbatim."""
    from tests.oql.oql_v2 import parse as p
    rows = lambda oql: p(oql).to_dict()["filter_rows"]
    assert rows("works where type is Article")[0]["value"] == "article"
    assert rows("works where language is EN")[0]["value"] == "en"
    assert rows("works where author country is br")[0]["value"] == "BR"
    assert rows("works where institution is I33213144")[0]["value"] == "I33213144"  # preserved
    assert rows("works where country is col_eu27")[0]["value"] == "col_eu27"        # preserved


def test_unparenthesized_or_connective_is_not_absorbed_into_value():
    """An `or` connective between two full `field is value` comparisons parses to
    an OR branch — it must NOT be swallowed into the preceding value.

    Regression guard for the production-`oql_parser.py` bug found via #373 live-verify
    (oxjob #363): `parse_oql_to_oqo("works where type is article or type is review")`
    once returned a single leaf `{column_id: type, value: "article or type is review"}`
    (count 0) instead of an OR of two leaves. Fixed by the #376 engine unification that
    made `parse_oql_to_oqo` delegate to the oracle grammar. This guards the **production
    entry point** the #373 OQL-submit pipeline calls, and the **un-parenthesized** shape
    (TestOQLParser.test_parse_or_expression only covers the parenthesized form). Distinct
    parser production from the `is any of (...)` value-list sugar (corpus rows 5 / 7)."""
    from query_translation.oql_parser import parse_oql_to_oqo

    # Same-field OR, no parens.
    fr = parse_oql_to_oqo("works where type is article or type is review").to_dict()["filter_rows"]
    assert len(fr) == 1
    branch = fr[0]
    assert branch.get("join") == "or"
    assert [f["value"] for f in branch["filters"]] == ["article", "review"]
    assert [f["column_id"] for f in branch["filters"]] == ["type", "type"]

    # Three-way OR stays flat — no value carries an `or ... is ...` tail.
    fr3 = parse_oql_to_oqo(
        "works where type is article or type is review or type is book"
    ).to_dict()["filter_rows"]
    assert len(fr3) == 1 and fr3[0]["join"] == "or"
    assert [f["value"] for f in fr3[0]["filters"]] == ["article", "review", "book"]


def test_canonical_output_is_lowercase_connectives():
    from tests.oql.oql_v2 import parse as p, render as r
    # different-column OR won't factor into `any of`, so an `or` survives to output
    out = r(canonicalize_oqo(p("works where it's open access AND (institution is I1 OR type is article)")))
    assert " and " in out and " or " in out
    assert " AND " not in out and " OR " not in out


def test_renderer_resolves_display_names_for_id_and_country_columns():
    from tests.oql.oql_v2 import parse as p, render as r
    names = {"I33213144": "Harvard University", "DE": "Germany", "article": "SHOULD-NOT-APPEAR"}
    out = r(canonicalize_oqo(p("works where institution is I33213144 and country is de and type is article")),
            resolver=lambda v: names.get(v))
    assert "[Harvard University]" in out      # opaque ID resolves
    assert "[Germany]" in out                 # country code resolves
    assert "[SHOULD-NOT-APPEAR]" not in out   # readable slug (article) does NOT


def test_search_model_space_quotes_near():
    """Lock the v2 search model under the #363 grammar after the D2 reversal
    (oxjob #363, discovery run #3): a maximal run of bare words inside a group is
    ONE stemmed adjacency-boosted node (NOT per-word AND); explicit and/or/not
    build the tree; 2+ bare terms at top level still must be parenthesized;
    quotes=exact, near=stemmed phrase."""
    from tests.oql.oql_v2 import parse as p, OQLError
    rows = lambda oql: p(oql).to_dict()["filter_rows"]

    # SPACE inside a group = ONE stemmed node (#1, D2 reversal). The engine
    # adjacency-boosts the whole run, so it is a single value, not climate AND
    # change (which would silently drop the match_phrase boost).
    fr = rows("works where title contains (climate change)")
    assert fr == [{"column_id": "display_name.search", "value": "climate change", "operator": "contains"}]

    # 2+ BARE terms (no parens) are a loud error — the footgun killer (D1) still
    # holds at the TOP level (the canonical render always parenthesizes).
    with pytest.raises(OQLError) as e:
        p("works where title contains climate change")
    assert e.value.code == "OQL_UNDELIMITED_TERM_LIST"

    # QUOTES = exact adjacent phrase (.search.exact) — one atom, bare is fine
    fr = rows('works where title contains "climate change"')
    assert fr == [{"column_id": "display_name.search.exact", "value": '"climate change"', "operator": "contains"}]

    # NEAR = stemmed adjacent phrase (.search, quoted value) — one atom, bare ok
    fr = rows('works where title contains near "whopper junior"')
    assert fr == [{"column_id": "display_name.search", "value": '"whopper junior"', "operator": "contains"}]

    # an embedded QUOTED token is an escape — a literal stemmed word folded into
    # the run, so a reserved word can live inside a stemmed value (#2)
    fr = rows('works where title contains (climate change "and" warming)')
    assert fr == [{"column_id": "display_name.search", "value": "climate change and warming", "operator": "contains"}]

    # single quoted word = exact; bare word = stemmed
    assert rows('works where title contains "cat"')[0]["column_id"] == "display_name.search.exact"
    assert rows("works where title contains cat")[0]["column_id"] == "display_name.search"

    # a bare run + explicit `or` = two nodes, NO mixed-bool error (the run is one
    # node, so there is no space-AND to mix with the or). (#1, D2 reversal)
    fr = rows("works where title contains (climate change or warming)")
    assert len(fr) == 1 and fr[0]["join"] == "or"
    assert sorted(f["value"] for f in fr[0]["filters"]) == ["climate change", "warming"]
    # explicit and+or at one level is still a loud mixed-bool error
    with pytest.raises(OQLError) as e:
        p("works where title contains (climate and change or warming)")
    assert e.value.code == "OQL_MIXED_BOOL_NEEDS_PARENS"
    # the disambiguated forms are fine
    p("works where title contains (climate (change or warming))")   # ok
    p("works where title contains ((climate change) or warming)")   # ok

    # a bare `not` at top level must be parenthesized; inside a group `not` binds
    # to the single next operand (tightest): `(not a and b)` = (not a) and b
    with pytest.raises(OQLError):
        p("works where title contains not a")
    fr = rows("works where title contains (not a and b)")  # top-level AND flattens
    by_val = {f["value"]: f.get("is_negated", False) for f in fr}
    assert by_val == {"a": True, "b": False}  # only `a` is negated


def test_corpus_covers_every_locked_behavior():
    """Spec self-check: each EXPLORE §2 locked behavior has >=1 corpus case."""
    ids = {r["id"] for r in ROWS}
    # Row ids are opaque sequential ints since #360; the old semantic ids are in
    # the trailing comments (full map: work/id_map.yaml).
    required = {
        # entity refs, sets, annotations            (ENT1,ENT3,ENT4,ENT5,ENT6)
        1, 3, 4, 5, 6,
        # booleans / precedence / casing            (BOOL1..BOOL4)
        7, 8, 9, 10,
        # the 9 gauntlet cases                       (G1..G9; G7b=18 excluded)
        11, 12, 13, 14, 15, 16, 17, 19, 20,
        # proximity / wildcard / semantic / exact / stemmed-phrase
        # (PW1,PW4,PW6,PW7,PW8,PW9,PW10,PW11,PW12)
        21, 24, 26, 27, 28, 29, 30, 31, 32,
    }
    missing = required - ids
    assert not missing, f"corpus missing locked-behavior cases: {sorted(missing)}"


OXURL_STATUSES = {"has-oxurl", "oql-only", "translator-bug", "server-unsupported"}


def test_every_row_has_valid_facets():
    """Every case carries a `category` (topical) facet and a structured
    `provenance` (real origin) facet; every ok/hint row also carries an explicit
    `oxurl_status` (#384, replacing the old `oxurl_representable` bool). These
    replaced the old conflated `group` / coarse `source` fields (#345); keeping
    them mechanical means the dev playground never has to infer semantics from
    the ID prefix."""
    categories = {
        "entity references", "boolean logic", "search semantics",
        "proximity & wildcards", "filter, sort & sample", "group by",
        "librarian & SR queries",
    }
    provenance_types = {
        "spec design", "analytics question", "librarian guide",
        "vendor docs", "zendesk ticket", "systematic review",
    }
    bad = []
    for r in ROWS:
        prov = r.get("provenance") or {}
        ok = (
            r.get("category") in categories
            and isinstance(prov, dict)
            and prov.get("type") in provenance_types
            and bool(prov.get("label"))
        )
        if r["status"] in ("ok", "hint"):
            # ok rows carry an oxurl_status enum; error / out-of-scope rows are
            # non-queries and carry neither oxurl_status nor oxurl.
            ok = ok and r.get("oxurl_status") in OXURL_STATUSES
        else:
            ok = ok and "oxurl_status" not in r and "oxurl" not in r
        if not ok:
            bad.append((r["id"], r.get("category"), prov.get("type"),
                        r.get("oxurl_status")))
    assert not bad, f"rows with missing/unknown facets: {bad}"

    # The non-`has-oxurl` ok rows are a deliberate, reviewed list. If this drifts
    # it's a real editorial change — update the map, don't loosen the assert.
    #   server-unsupported — valid OQO the live API can't execute yet.
    #   oql-only           — valid OQO that OXURL genuinely can't express (a win).
    #   translator-bug     — should render per spec but the translator is wrong.
    # (oxjob #384: row 30's semantic-search "translator gap" was fixed by #363 —
    #  it now renders ?search.semantic= and is `has-oxurl`, so there is currently
    #  no `translator-bug` row.)
    non_has_oxurl = {
        r["id"]: r["oxurl_status"]
        for r in OK_ROWS if r["oxurl_status"] != "has-oxurl"
    }
    expected = {
        # row 48 (AKQ#75 multi-dim group_by) was server-unsupported; oxjob #387
        # shipped nested execution, so it is now `has-oxurl`.
        78: "oql-only",            # zd#8101 OR across stemmed/exact match-modes
        87: "oql-only",            # cross-field OR (title vs. abstract); #363
        91: "oql-only",            # nested AND inside an OR search group; #363
        # Real mined SR strategies (#434 -> #363). oql-only because the OR-group
        # mixes quoted phrases (no-stem .search.exact) with bare words (stemmed
        # .search), or nests an AND inside an OR, or ORs across fields — none of
        # which classic URL `filter=` syntax can express. The expressiveness win.
        142: "oql-only", 145: "oql-only", 147: "oql-only", 148: "oql-only",
        151: "oql-only", 152: "oql-only", 153: "oql-only", 154: "oql-only",
        155: "oql-only", 156: "oql-only", 157: "oql-only", 159: "oql-only",
        160: "oql-only",
        # zd#8101 Claire's remaining real SR strategies (Vaping & Health,
        # Educational accountability). All oql-only — each ORs quoted phrases
        # against bare/stemmed words (and uses within-field NOT), which classic
        # URL `filter=` syntax can't express. (162 is her own mis-quoted line,
        # an `error` footgun row — not in this ok-row map.)
        161: "oql-only", 163: "oql-only", 164: "oql-only",
        165: "oql-only", 166: "oql-only", 167: "oql-only",
    }
    assert non_has_oxurl == expected, (
        f"oxurl_status classification drifted: "
        f"+{set(non_has_oxurl) - set(expected)} -{set(expected) - set(non_has_oxurl)}"
    )


def test_corpus_oxurl_is_canonical():
    """`oxurl` is a DERIVED field — every ok/hint row's stored value must equal a
    fresh render of its OQO (oxjob #384). This is the elastic-api side of the
    drift gate: edit an oql/oqo without re-running docs/oql/regen_corpus_oql.py
    and this goes red. `oql-only` rows (the renderer raises) store null.

    Invariant the playground relies on: oxurl is null IFF the row is oql-only."""
    import sys
    sys.path.insert(0, os.path.dirname(CORPUS))  # docs/oql/
    from regen_corpus_oql import build_oxurl, canonical_oqo_dict

    stale = []
    for r in OK_ROWS:
        want = build_oxurl(canonical_oqo_dict(r))
        if r.get("oxurl") != want:
            stale.append((r["id"], r.get("oxurl"), want))
        is_null = r.get("oxurl") is None
        is_oql_only = r["oxurl_status"] == "oql-only"
        assert is_null == is_oql_only, (
            f"{r['id']}: oxurl null ({is_null}) must match oql-only "
            f"({is_oql_only}) — status={r['oxurl_status']}")
    assert not stale, (
        "oxurl is stale — run `python docs/oql/regen_corpus_oql.py`:\n  "
        + "\n  ".join(f"{i}: stored={s!r} fresh={w!r}" for i, s, w in stale))
