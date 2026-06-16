"""Fixes from Jason's random-search walkthrough batch 3 (oxjob #363, discovery run #3).

A single real SERP URL (a top-percentile Alzheimer-mouse-model systematic-review
search) surfaced three independent translator bugs:

  W3.1. A scoped `search.title_and_abstract=…` URL param is folded into the filter
        string. The fold joined with ", " (comma + SPACE); the filter-clause
        splitter does not trim, so the column id became " title_and_abstract.search"
        (leading space) -> `invalid_column`. The engine itself rejects a
        space-prefixed column, so the join must use a bare comma.
  W3.2. The friendly sort key `citation percentile by subfield` is FOUR words, but
        `_parse_sort_field` hand-rolled a 3-word longest-match loop (the filter path
        uses the shared 4-word `match_field`). So the key parsed in `where` but
        raised OQL_TRAILING_TOKENS in `sort by`. Fixed by pointing the sort path at
        the shared matcher.
  W3.3. A quoted single "word" that the analyzer splits into >1 subtoken (a
        hyphen/slash token like "3xTg-AD" / "APP/PS1") is NOT equivalent to the bare
        form on a STEMMED .search column: quoted = adjacent subtokens, bare =
        subtokens AND'd (measured live: `"3xTg-AD"` 2027 vs `3xTg-AD` 2354;
        `"APP/PS1"` 6440 vs 8056). The encoder dropped quotes for any single
        whitespace-token, so `near "3xTg-AD"` re-parsed to bare `3xTg-AD` (a silent
        recall change). Now multi-subtoken stemmed tokens keep their quotes; atomic
        tokens (5xFAD, covid19 — measured equal) and exact-column wildcards
        ("foo*bar") stay bare.

Run with:
    PYTHONPATH=. pytest tests/oql/test_search_walkthrough_4.py -q
"""
import pytest

import tests.oql._qt_loader  # noqa: F401  (installs the pure query_translation stub)

from query_translation.oql_lang import parse, render_tree, OQLError  # noqa: E402
from query_translation.oqo_canonicalizer import canonicalize_oqo  # noqa: E402
from query_translation.url_parser import parse_url_to_oqo  # noqa: E402
from query_translation.validator import validate_oqo  # noqa: E402
from query_translation.views import _parse_oxurl_value  # noqa: E402


# Jason's reported URL (search.title_and_abstract scoped param + 4-word sort key).
JASON_OXURL = (
    "works?filter=publication_year:2023-2025,type:article,language:en,"
    "primary_location.source.type:journal,citation_normalized_percentile.value:0.99-1,"
    "fwci:1.00-100&sort=citation_normalized_percentile.value:desc"
    '&search.title_and_abstract=("Alzheimer disease" OR "Alzheimer\'s disease") '
    'AND ("mouse model" OR "transgenic mouse" OR "APP/PS1" OR "3xTg-AD" OR "5xFAD" OR "in vivo")'
)


def _render(oqo):
    return render_tree(canonicalize_oqo(oqo))[0]


# --------------------------------------------------------------------------- #
# W3.1 — scoped search.<scope>= fold must not inject a leading-space column
# --------------------------------------------------------------------------- #
def test_w31_scoped_search_fold_has_no_leading_space():
    oqo, err = _parse_oxurl_value(JASON_OXURL)
    assert err is None
    vr = validate_oqo(oqo).to_dict()
    assert vr["valid"], vr["errors"]
    # no folded leaf may carry a space-prefixed column id
    cols = []
    for row in oqo.to_dict()["filter_rows"]:
        cols.extend(f["column_id"] for f in row.get("filters", [row]))
    assert all(c == c.strip() for c in cols), cols
    assert "title_and_abstract.search" in cols  # the scoped search actually folded in


def test_w31_simple_scoped_search_folds_clean():
    oqo, err = _parse_oxurl_value("works?search.title_and_abstract=climate")
    assert err is None
    assert validate_oqo(oqo).to_dict()["valid"]
    leaf = oqo.to_dict()["filter_rows"][0]
    leaf = leaf.get("filters", [leaf])[0] if "filters" in leaf else leaf
    assert leaf["column_id"] == "title_and_abstract.search"  # no leading space


# --------------------------------------------------------------------------- #
# W3.2 — a 4-word curated alias is a valid sort key (parity with the filter path)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sort_key", [
    "citation percentile by subfield",   # 4 words — the regression
    "cited by count",                    # 3 words — already worked, guard it
    "FWCI",                              # 1 word
])
def test_w32_multiword_sort_key_parses(sort_key):
    parse(f"works sort by {sort_key} desc")  # must not raise OQL_TRAILING_TOKENS


def test_w32_same_alias_works_in_where_and_sort():
    # the 4-word alias resolves in both a where comparison clause and sort by
    # (the dash range `0.99-1` was removed in decision 24 -> endpoint clauses).
    parse("works where citation percentile by subfield >= 0.99 "
          "and citation percentile by subfield <= 1")
    parse("works sort by citation percentile by subfield desc")


# --------------------------------------------------------------------------- #
# W3.3 — quoted multi-subtoken stemmed token keeps its quotes; atomic stays bare
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token", ["3xTg-AD", "APP/PS1"])
def test_w33_multisubtoken_stemmed_token_keeps_quotes(token):
    # `near "X"` = stemmed adjacent phrase; for a hyphen/slash token it must NOT
    # collapse to bare (different result set on the engine).
    oqo = parse(f'works where title/abstract has (near "{token}")')
    leaf = oqo.to_dict()["filter_rows"][0]
    leaf = leaf.get("filters", [leaf])[0] if "filters" in leaf else leaf
    assert leaf["value"] == f'"{token}"', leaf
    assert leaf["column_id"].endswith(".search")  # stemmed, not .search.exact


@pytest.mark.parametrize("token", ["5xFAD", "covid19", "cat"])
def test_w33_atomic_stemmed_token_stays_bare(token):
    # an atomic alphanumeric token is not split by the analyzer (measured equal),
    # so it stays bare so the common case isn't gratuitously quoted.
    oqo = parse(f'works where title/abstract has (near "{token}")')
    leaf = oqo.to_dict()["filter_rows"][0]
    leaf = leaf.get("filters", [leaf])[0] if "filters" in leaf else leaf
    assert leaf["value"] == token, leaf


def test_w33_exact_column_wildcard_token_stays_bare():
    # regression guard for corpus rows 22/23/60: a wildcard pattern on the EXACT
    # column ("foo*bar") must stay bare — `*`/`?` are metachars, not delimiters,
    # and the subtoken exception is stemmed-only.
    oqo = parse('works where title has "foo*bar"')
    leaf = oqo.to_dict()["filter_rows"][0]
    assert leaf["value"] == "foo*bar"
    assert leaf["column_id"].endswith(".search.exact")


# --------------------------------------------------------------------------- #
# End-to-end: the whole reported URL renders OQL that re-parses (no error)
# --------------------------------------------------------------------------- #
def test_w3_full_url_renders_reparseable_oql():
    oqo, err = _parse_oxurl_value(JASON_OXURL)
    assert err is None
    oql = _render(oqo)
    parse(oql)  # the headline guarantee: the displayed OQL re-parses cleanly


def test_w3_full_url_render_is_semantically_stable():
    # parser self-consistency: render -> parse -> render is a fixed point
    oqo, _ = _parse_oxurl_value(JASON_OXURL)
    oql1 = _render(oqo)
    oql2 = _render(parse(oql1))
    assert oql2 == _render(parse(oql2))  # second render is the fixed point
    # multi-subtoken phrases kept their quotes; the atomic token went bare
    assert 'near "3xTg-AD"' in oql2
    assert 'near "APP/PS1"' in oql2
    assert "5xFAD" in oql2 and '"5xFAD"' not in oql2  # bare, unquoted atom
