"""oxjob #365: a word that mixes letters and digits also finds its split spelling.

Removing subscript markup left formulas split in the stored text: "vitamin B 12" (the
legacy abstract of W1536233415, ZD 8030), "Ground state of BaFe 2 S 3" and "... Mn 4 N
thin films" (Physical Review MathML titles, ZD 3918), "CO 2" in ~370K abstracts. The
standard tokenizer keeps a typed `b12` whole, so it never met the tokens `b` `12`.
build_query now ORs (dis_max) in the word read as the phrase of its parts. Not under NOT,
not on semantic / author-name / raw-affiliation searches, never over full text.
No ES: the keyword lookup is stubbed.
"""
import json

import pytest

from core.search import SearchOpenAlex, full_search_query, full_search_query_exact, scoped_search_query


@pytest.fixture(autouse=True)
def no_keyword_lookup(monkeypatch):
    import core.keyword_search as ks
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: [] for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


def _dump(q):
    return json.dumps(q.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize(
    "typed, variant",
    [
        ("b12", '"b 12"'),
        ("B12", '"B 12"'),
        ("vitamin B12 producer", 'vitamin "B 12" producer'),
        ("BaFe2S3", '"BaFe 2 S 3"'),
        ("Mn4N thin films", '"Mn 4 N" thin films'),
        ("pm2.5 exposure", '"pm 2.5" exposure'),
        ("covid19", '"covid 19"'),
        ("il6", '"il 6"'),
        ("vitamin d3", 'vitamin "d 3"'),
        ("CO2.", '"CO 2".'),
        ("b12, folate", '"b 12", folate'),
        # boolean, as in ZD 8030 (the wildcard words keep their form)
        ("B12 AND (product* OR biosynthes*)", '"B 12" AND (product* OR biosynthes*)'),
        ("(b12 OR co2) AND deficiency", '("b 12" OR "co 2") AND deficiency'),
        # inside a quoted phrase the parts just join the phrase
        ('"vitamin b12 producer"', '"vitamin b 12 producer"'),
        ('"b12 deficiency"~3', '"b 12 deficiency"~3'),
        ('"vitamin b12" metabolism', '"vitamin b 12" metabolism'),
    ],
)
def test_variant(typed, variant):
    s = SearchOpenAlex(search_terms=typed, primary_field="display_name")
    v = s.formula_split_spelling()
    assert v is not None and v.search_terms == variant
    body = _dump(s.build_query(skip_citation_boost=True))
    assert '"dis_max"' in body


@pytest.mark.parametrize(
    "terms",
    [
        "machine learning",  # no digit
        "2020 elections",  # digits alone
        "COVID-19 vaccines",  # the tokenizer splits at the hyphen already
        "10.1038/nature12373",  # glued to other punctuation
        "co2-capturing",
        "b12*",  # a wildcard word keeps its form
        "b12 NOT folate",  # OR-ing spellings under NOT lets one through
        "NOT b12",
        '"unbalanced b12',  # odd quotes: leave it to the parser as typed
        "a1b2c3d4e5f6a7b8c9",  # an id or hash, not a formula
        "e.coli2",  # a dot between letters
        "3d printing",  # number first: split it reads as a unit ("3 d" = 3 days)
        "5g networks",  # "5 g" = 5 grams
        "10mg",
        # leading letters that read as prose before a number: "Vol. 18, No. 2", "p. 53", "n = 2"
        "no2",
        "As2S3 films",
        "p53 mutation",
        "n2 adsorption",
        "Fig3",
    ],
)
def test_no_variant(terms):
    s = SearchOpenAlex(search_terms=terms, primary_field="display_name")
    assert s.formula_split_spelling() is None


def test_plain_search_unchanged_without_mixed_word():
    s = SearchOpenAlex(search_terms="vitamin deficiency", primary_field="display_name")
    assert '"dis_max"' not in _dump(s.build_query(skip_citation_boost=True))


def test_whole_query_not_excludes_both_spellings():
    # `NOT x` is built as the complement of x's own query, so both spellings are excluded.
    s = SearchOpenAlex(search_terms="NOT b12", primary_field="display_name")
    must_not = s.build_query(skip_citation_boost=True).to_dict()["bool"]["must_not"]
    body = json.dumps(must_not, ensure_ascii=False)
    assert '\\"b 12\\"' in body and '"b12"' in body


def test_semantic_and_author_searches_have_no_variant():
    assert SearchOpenAlex(search_terms="b12 deficiency", is_semantic_query=True).formula_split_spelling() is None
    assert SearchOpenAlex(search_terms="Smith2", is_author_name_query=True).formula_split_spelling() is None
    assert SearchOpenAlex(
        search_terms="Lab 2B", primary_field="authorships.raw_affiliation_strings"
    ).formula_split_spelling() is None


def test_title_and_abstract_filter_carries_the_split_phrase():
    # ZD 8030: title_and_abstract.search:b12 must reach "vitamin B 12" in an abstract.
    body = _dump(scoped_search_query("b12", "title_and_abstract", "default"))
    assert '"dis_max"' in body
    assert '\\"b 12\\"' in body
    assert "display_name" in body and "abstract" in body


def test_title_exact_filter_carries_the_split_phrase():
    body = _dump(scoped_search_query("BaFe2S3", "title", "exact"))
    assert '\\"BaFe 2 S 3\\"' in body and "display_name.no_stem" in body


def test_variant_never_reads_full_text():
    for q in (full_search_query("works", "co2 capture"), full_search_query_exact("co2 capture")):
        d = q.to_dict()
        body = json.dumps(d, ensure_ascii=False)
        assert '\\"co 2\\" capture' in body
        # every clause holding the split phrase reads titles and abstracts only
        def walk(node):
            if isinstance(node, dict):
                qs = node.get("query_string")
                if qs and '"co 2"' in qs.get("query", ""):
                    fields = qs.get("fields") or [qs.get("default_field")]
                    assert not any(f.split("^")[0].startswith("fulltext") for f in fields), fields
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(d)


def test_fulltext_only_search_has_no_variant():
    s = SearchOpenAlex(search_terms="co2", primary_field="fulltext")
    assert s.formula_split_spelling() is None


def test_curly_and_formula_variants_compose():
    s = SearchOpenAlex(search_terms="Hartmann's b12", primary_field="display_name")
    q = s.build_query(skip_citation_boost=True).to_dict()
    assert len(q["dis_max"]["queries"]) == 3

