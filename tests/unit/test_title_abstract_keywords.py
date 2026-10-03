"""Title + abstract + keywords search and rerank=true (oxjob #1521). No ES: the
keyword lookup is stubbed; the live checks live in the oxjob's scratch/tak_live_check.py."""
import json

import pytest

import settings
from core import keyword_search as ks
from core import rerank
from core.exceptions import APIQueryParamsError
from core.search import SearchOpenAlex, scoped_search_query, works_keyword_search_query

KW = {
    "remote work": ["https://openalex.org/keywords/remote-work"],
    "productivity": ["https://openalex.org/keywords/productivity"],
    "no": ["https://openalex.org/keywords/nitric-oxide"],
}


@pytest.fixture(autouse=True)
def stub_lookup(monkeypatch):
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: list(KW.get(s.lower(), [])) for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


def rec(q):
    return json.loads(ks.keyword_record(q))


def test_longest_span_wins_and_every_part_is_anded():
    r = rec("remote work productivity")
    assert [s for s, _ in r["segments"]] == ["remote work", "productivity"]
    assert r["leftover"] == []


def test_leftover_words_must_be_in_text():
    r = rec("remote work burnout")
    assert [s for s, _ in r["segments"]] == ["remote work"]
    assert r["leftover"] == ["burnout"]
    body = ks.with_keywords("remote work burnout", r, {"match_all": {}}, ["display_name", "abstract^0.1"])
    must = body["bool"]["should"][1]["bool"]["must"]
    assert must[0]["bool"]["should"][1] == {"terms": {"keywords.id": KW["remote work"]}}
    assert must[1]["multi_match"]["query"] == "burnout"


def test_stopword_span_is_never_a_keyword():
    # "NO" is a keyword synonym (nitric oxide) but an English stopword.
    assert rec("NO evidence")["segments"] == []


def test_rule_is_ored_with_the_text_query():
    base = {"match": {"display_name": "remote work productivity"}}
    body = ks.with_keywords("remote work productivity", rec("remote work productivity"), base, ["display_name"])
    assert body["bool"]["should"][0] == base
    assert body["bool"]["minimum_should_match"] == 1


def test_no_keywords_returns_the_text_query_unchanged():
    base = {"match": {"display_name": "graphene"}}
    assert ks.with_keywords("graphene", rec("graphene"), base, ["display_name"]) == base
    assert ks.keyword_bonus(base, rec("graphene")) == base


def test_boolean_leaves_get_keyword_alternatives():
    q = '"remote work" AND productivity'
    base = {"query_string": {"query": q, "fields": ["display_name"]}}
    body = ks.with_keywords(q, rec(q), base, ["display_name"])
    assert body["query_string"]["query"] == (
        '("remote work" OR keywords.id:"https://openalex.org/keywords/remote-work") AND '
        '(productivity OR keywords.id:"https://openalex.org/keywords/productivity")'
    )


def test_keyword_bonus_is_split_over_groups():
    body = ks.keyword_bonus({"match_all": {}}, rec("remote work productivity"))
    assert [c["constant_score"]["boost"] for c in body["bool"]["should"]] == [5.0, 5.0]


def test_long_pasted_text_skips_the_lookup():
    q = " ".join(["word"] * (ks.MAX_LOOKUP_TOKENS + 1))
    assert rec(q)["segments"] == []


def test_scoped_search_wraps_title_abstract_with_saturation(monkeypatch):
    import core.search as cs
    monkeypatch.setattr(cs.settings, "CITATION_SCALING", "sat", raising=False)
    d = scoped_search_query("remote work productivity", "title_abstract_keywords", "default").to_dict()
    script = d["function_score"]["functions"][0]["script_score"]["script"]["source"]
    assert "c / (c + 100.0)" in script
    assert "fulltext" not in json.dumps(d)


def test_broad_search_keeps_fulltext():
    d = works_keyword_search_query("remote work productivity", with_fulltext=True, skip_citation_boost=True).to_dict()
    assert "fulltext" in json.dumps(d)


def test_citation_scaling_switch_reverts_to_sqrt(monkeypatch):
    import core.search as cs
    monkeypatch.setattr(cs.settings, "CITATION_SCALING", "sqrt", raising=False)
    d = scoped_search_query("graphene", "title_and_abstract", "default").to_dict()
    assert "Math.sqrt" in d["function_score"]["functions"][0]["script_score"]["script"]["source"]


def test_non_works_entities_keep_sqrt():
    d = SearchOpenAlex(search_terms="smith").build_query().to_dict()
    assert "Math.sqrt" in d["function_score"]["functions"][0]["script_score"]["script"]["source"]


# ---------- rerank ----------

def params(**kw):
    p = {"search": "remote work", "search_type": "default", "searches": [], "filters": None, "group_by": None,
         "group_bys": None, "sample": None, "sort": None, "cursor": None, "page": 1, "per_page": 25}
    p.update(kw)
    return p


@pytest.mark.parametrize("kw", [
    {"sort": {"cited_by_count": "desc"}},
    {"group_by": "type"},
    {"sample": 10},
    {"search": None},
    {"search_type": "semantic"},
])
def test_rerank_conflicts_are_400s(kw):
    with pytest.raises(APIQueryParamsError):
        rerank.validate(params(**kw), "works")


def test_rerank_allows_relevance_sort_and_search_filters():
    rerank.validate(params(sort={"relevance_score": "desc"}), "works")
    rerank.validate(params(search=None, filters=[{"title_abstract_keywords.search": "remote work"}]), "works")


def test_rerank_only_on_works():
    with pytest.raises(APIQueryParamsError):
        rerank.validate(params(), "authors")


def test_rerank_cursor_round_trips_and_rejects_garbage():
    c = rerank.encode_rerank_cursor(25, rerank.CACHE_PREFIX + "abc")
    assert rerank.is_rerank_cursor(c)
    assert rerank.decode_rerank_cursor(c) == {"o": 25, "k": rerank.CACHE_PREFIX + "abc"}
    assert rerank.decode_rerank_cursor("*") is None
    with pytest.raises(APIQueryParamsError):
        rerank.decode_rerank_cursor(rerank.CURSOR_PREFIX + "not-base64!")


def test_breaker_opens_after_five_failures():
    b = rerank.Breaker(failures=5, window_s=30, open_s=60)
    for _ in range(4):
        b.record(False)
    assert b.allow()
    b.record(False)
    assert not b.allow()


def test_jev_failure_returns_none(monkeypatch):
    monkeypatch.setattr(rerank.settings, "TYPESAFE_API_KEY", "x", raising=False)
    monkeypatch.setattr(rerank, "breaker", rerank.Breaker())

    def boom(*a, **k):
        raise TimeoutError

    monkeypatch.setattr(rerank._session, "post", boom)
    assert rerank.jev_probabilities("q", [{"title": "t", "venue": "v", "year": 2020, "type": "article"}]) is None


def test_oqo_query_text_collects_search_leaves_only():
    rows = [
        {"column_id": "title_abstract_keywords.search", "value": "coral bleaching", "operator": "has"},
        {"join": "or", "filters": [{"column_id": "abstract.search", "value": "reef"},
                                   {"column_id": "title.search", "value": "heat", "is_negated": True}]},
        {"column_id": "publication_year", "value": 2020},
    ]
    assert rerank.oqo_query_text(rows) == "coral bleaching ; reef"


def test_cache_key_ignores_oqo_view_fields():
    class Req:
        class args:
            @staticmethod
            def items(multi=True):
                return []
    a = rerank.cache_key(Req, "works", {"filter_rows": [1], "page": 1, "per_page": 25})
    b = rerank.cache_key(Req, "works", {"filter_rows": [1], "page": 3, "per_page": 10, "cursor": "x", "select": ["id"]})
    c = rerank.cache_key(Req, "works", {"filter_rows": [2]})
    assert a == b != c
