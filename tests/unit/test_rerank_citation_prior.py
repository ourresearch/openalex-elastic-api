"""rerank=true: the gated citation prior in the final sort. No ES, no Jev: the Search and
Jev's probabilities are stubbed. The p and citation counts in the scenarios are real values
from live Jev calls (jev-1.13.0) on the top 100 of `search=<title>`."""
import pytest

from core import rerank


class FakeResp:
    def __init__(self, hits):
        self._hits = hits
        self.hits = type("H", (), {"total": type("T", (), {"value": len(hits)})})

    def to_dict(self):
        return {"hits": {"hits": self._hits}}


class FakeSearch:
    def __init__(self, hits):
        self._hits = hits

    def source(self, fields):
        self.fields = fields
        return self

    def extra(self, **kw):
        return self

    def execute(self):
        return FakeResp(self._hits)


def hit(i, title, cites, year=2020, venue="V", type_="article"):
    return {"_source": {"id": i, "display_name": title, "publication_year": year, "type": type_,
                        "cited_by_count": cites, "primary_location": {"source": {"display_name": venue}}},
            "sort": [1.0, i]}


def order_for(hits, p, monkeypatch):
    """compute_order() with Jev stubbed to return p; returns (ids in final order, cached scores)."""
    monkeypatch.setattr(rerank, "jev_probabilities", lambda q, cands: list(p))
    cached = {}
    monkeypatch.setattr(rerank, "cache_set", lambda key, entry: cached.update(entry))
    monkeypatch.setattr(rerank, "record", lambda *a, **k: None)
    entry = rerank.compute_order(FakeSearch(hits), {"search": "q"}, "k", query="q")
    return entry["ids"], entry["scores"]


# ---------- blended() ----------

def test_no_boost_without_citations_or_at_the_floor():
    assert rerank.blended(0.9, 0) == 0.9
    assert rerank.blended(0.9, None) == 0.9
    assert rerank.blended(rerank.settings.RERANK_CITATION_FLOOR, 10**6) == rerank.settings.RERANK_CITATION_FLOOR
    assert rerank.blended(0.3, 10**6) == 0.3  # below the floor: p unchanged


def test_boost_grows_with_citations_and_saturates():
    p = 0.9
    vals = [rerank.blended(p, c) for c in (0, 10, 100, 10_000, 10**9)]
    assert vals == sorted(vals)
    assert vals[-1] == pytest.approx(p * (1 + rerank.settings.CITATION_MAX_BOOST * (p - 0.5) / 0.5), rel=1e-3)
    assert rerank.blended(1.0, 10**9) == pytest.approx(1 + rerank.settings.CITATION_MAX_BOOST, rel=1e-3)


def test_weak_match_cannot_jump_a_strong_one():
    # p=0.55 with 100k citations (0.58) must stay under p=0.80 with none.
    assert rerank.blended(0.55, 100_000) < rerank.blended(0.80, 0)


def test_off_switch_returns_p(monkeypatch):
    monkeypatch.setattr(rerank.settings, "RERANK_CITATION_PRIOR", False, raising=False)
    assert rerank.blended(0.9, 10**6) == 0.9


def test_floor_of_one_does_not_divide_by_zero(monkeypatch):
    monkeypatch.setattr(rerank.settings, "RERANK_CITATION_FLOOR", 1.0, raising=False)
    assert rerank.blended(0.9, 100) > 0


# ---------- compute_order(): the real scenarios ----------

def test_attention_is_all_you_need_original_beats_its_summary_and_review(monkeypatch):
    hits = [
        hit("W_original", "Attention Is All You Need", 78297, year=2025, venue="", type_="preprint"),
        hit("W_summary", "5分で分かる! 有名論文ナナメ読み：Ashish Vaswani et al. : Attention Is All You Need", 0, 2018),
        hit("W_review", "Attention Is All You Need: A Technical Review of the Transformer", 0, 2026),
    ]
    ids, scores = order_for(hits, [0.79, 0.79, 0.82], monkeypatch)
    assert ids == ["W_original", "W_review", "W_summary"]
    assert scores == [0.79, 0.82, 0.79]  # rerank_score stays Jev's raw p


def test_generative_adversarial_networks_original_beats_look_alikes(monkeypatch):
    hits = [
        hit("W_overview", "Generative Adversarial Networks: An Overview", 4534, 2018),
        hit("W_gans", "Generative Adversarial Networks (GANs)", 704, 2021),
        hit("W_arxiv", "Generative Adversarial Networks", 4475, 2014),
        hit("W_cacm", "Generative adversarial networks", 18313, 2020),
    ]
    ids, _ = order_for(hits, [0.98, 0.98, 0.98, 0.97], monkeypatch)
    # p alone ranks the 18k-citation paper last of these four. The prior lifts it over the 704-citation
    # survey and level with the others; it takes a 0.01 p gap to separate them, so it does not reach #1
    # (that needs citations in Jev's state, not part of this change).
    assert ids.index("W_cacm") == 2
    assert ids[-1] == "W_gans"


def test_crowded_topic_established_papers_beat_uncited_lookalikes(monkeypatch):
    hits = [hit(f"new{i}", f"Antimicrobial resistance in hospital-acquired infections {i}", 0, 2026) for i in range(3)]
    hits += [hit("old_a", "Antimicrobial Resistance in Hospital-Acquired Gram-Negative Bacterial Infections", 220, 2015),
             hit("old_b", "The burden of hospital acquired infections and antimicrobial resistance", 139, 2023)]
    ids, _ = order_for(hits, [0.96, 0.94, 0.94, 0.93, 0.93], monkeypatch)
    assert ids[:2] == ["old_a", "old_b"]


def test_ties_and_zero_citations_fall_back_to_es_order(monkeypatch):
    hits = [hit(f"w{i}", f"t{i}", 0) for i in range(4)]
    ids, _ = order_for(hits, [0.8, 0.8, 0.8, 0.8], monkeypatch)
    assert ids == ["w0", "w1", "w2", "w3"]


def test_missing_citation_count_is_zero(monkeypatch):
    h = hit("a", "t", 5)
    del h["_source"]["cited_by_count"]
    ids, _ = order_for([h, hit("b", "u", 0)], [0.8, 0.8], monkeypatch)
    assert ids == ["a", "b"]


def test_off_switch_restores_p_only_order(monkeypatch):
    monkeypatch.setattr(rerank.settings, "RERANK_CITATION_PRIOR", False, raising=False)
    hits = [hit("review", "Attention Is All You Need: A Technical Review", 0),
            hit("original", "Attention Is All You Need", 78297)]
    ids, _ = order_for(hits, [0.82, 0.79], monkeypatch)
    assert ids == ["review", "original"]


def test_light_source_asks_for_the_citation_count():
    assert "cited_by_count" in rerank.LIGHT_SOURCE


# ---------- cache key ----------

class Req:
    class args:
        @staticmethod
        def items(multi=True):
            return [("search", "attention is all you need")]


def test_cache_key_changes_with_the_prior_settings(monkeypatch):
    base = rerank.cache_key(Req, "works")
    monkeypatch.setattr(rerank.settings, "RERANK_CITATION_FLOOR", 0.3, raising=False)
    floor = rerank.cache_key(Req, "works")
    monkeypatch.setattr(rerank.settings, "RERANK_CITATION_PRIOR", False, raising=False)
    off = rerank.cache_key(Req, "works")
    assert len({base, floor, off}) == 3
    assert all(k.startswith(rerank.CACHE_PREFIX) for k in (base, floor, off))
