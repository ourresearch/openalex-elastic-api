"""Echo gaps seen live after the default flip (oxjob #1555, 2026-11-03).

Each echo must say what the query does and read back to the same query.
"""
import pytest

from query_translation.oqo import OQO
from query_translation.oql_core import parse_core, render_core
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.validator import validate_oqo
from query_translation.analytics import _condition_label

WORKS_COLLECTION = {"col_x": "works"}.get


# --- a works collection combines with an order, a table or a condition ------------

@pytest.mark.parametrize("text", [
    "get works in the collection [Mine](col_x), most cited first",
    "get the count of works in the collection [Mine](col_x) by year",
    "get works since 2010 in the collection [Mine](col_x)",
])
def test_a_works_collection_combines(text):
    oqo = parse_core(text, WORKS_COLLECTION)
    leaf = next(f for f in oqo.filter_rows if getattr(f, "operator", None) == "in collection")
    assert leaf.column_id == "collection"          # as `?filter=collection:col_x` reads it
    assert validate_oqo(oqo).valid, validate_oqo(oqo).errors


def test_is_a_collection_means_membership():
    # `country is col_x` matched nothing (read as a literal ID) and echoed `get (col_x)'s works`
    from query_translation.oqo import LeafFilter
    oqo = canonicalize_oqo(OQO(get_rows="works", filter_rows=[
        LeafFilter("authorships.countries", "col_x"),
        LeafFilter("title.search", "kelp", "has")]))
    leaf = next(f for f in oqo.filter_rows if f.column_id == "authorships.countries")
    assert leaf.operator == "in collection"
    text = render_core(oqo)
    assert "'s works" not in text and "in the collection (col_x)" in text


def test_a_collection_url_echo_reads_back():
    # `/works?filter=collection:col_x&sort=cited_by_count:desc` echoed text that failed
    oqo = OQO.from_dict({"get_rows": "works",
                         "filter_rows": [{"column_id": "collection", "value": "col_x",
                                          "operator": "in collection"}],
                         "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}]})
    text = render_core(oqo)
    assert text == "get works in the collection (col_x), most cited first"
    assert canonicalize_oqo(parse_core(text, WORKS_COLLECTION)).to_dict() == canonicalize_oqo(oqo).to_dict()


# --- a compare's rows are labeled by what they hold ----------------------------------

@pytest.mark.parametrize("text,label", [
    ("country is [India](IN)", "country is India"),
    ("country is not [India](IN)", "country is not India"),        # was `country is India(IN)`
    ("institution is (I99464096 [KU Leuven])", "institution is (KU Leuven)"),   # today's form
    ("institution is (I1 [no entity found])", "institution is (I1)"),
    ("institution is (I63966007)", "institution is (I63966007)"),
])
def test_compare_labels(text, label):
    assert _condition_label(text) == label


# --- a thing's conditions in its own words ---------------------------------------------

def test_author_conditions_use_the_authors_words():
    oqo = OQO.from_dict({"get_rows": "authors", "filter_rows": [
        {"column_id": "summary_stats.h_index", "value": 100, "operator": ">"},
        {"column_id": "topics.subfield.id", "value": "1702"}]})
    text = render_core(oqo)
    assert "topics.subfield.id" not in text
    assert "where subfield is" in text


# --- the broad search names the three places it reads ----------------------------------

def test_broad_search_says_title_abstract_or_full_text():
    oqo = parse_core("get works with (kelp forests) in the title, abstract, or full text")
    assert render_core(oqo) == "get works with (kelp forests) in the title, abstract, or full text"


def test_the_old_place_still_reads():
    old = parse_core("get works with (kelp forests) in the full text")
    new = parse_core("get works with (kelp forests) in the title, abstract, or full text")
    assert old.to_dict() == new.to_dict()


@pytest.mark.parametrize("q", ["get works with kelp in the full text",
                               "get works with kelp in the title, abstract, or full text, most cited first",
                               "get works (all corpora) about kelp",
                               "get the count of articles (expansion corpus) about kelp by year"])
def test_the_editor_reads_both_places_whole(q):
    from query_translation import oql_core_context as X
    toks = X._tokens(q)
    w, stop = X._walk(q, toks, len(toks))
    assert isinstance(stop, X._Stop) and w.skipped == 0


# --- a split's own conditions read in the sentence -------------------------------------

@pytest.mark.parametrize("text", [
    "get the count of works about kelp by author where last known institution is (I141945490)",
    "get the count of works about kelp by institution where institution type is (education)",
    "get the count of works about kelp by author where co-author is not (A5023888391)",
    "get the count of works about kelp by author where last known institution is (I141945490) and year",
])
def test_a_split_with_its_own_conditions_is_one_sentence(text):
    oqo = parse_core(text)
    assert oqo.group_by[0].where is not None
    assert render_core(oqo) == text


def test_conditions_that_would_read_as_a_split_fall_back():
    # an `and country ...` inside the split's conditions would read as a second split
    oqo = OQO.from_dict({"get_rows": "works", "filter_rows": [], "group_by": [
        {"column_id": "authorships.institutions.lineage", "where": {"join": "and", "filters": [
            {"column_id": "type", "value": "education"},
            {"column_id": "country_code", "value": "KE", "is_negated": True}]}}],
        "calculate": [{"measure": "count"}]})
    text = render_core(oqo)
    assert text is None or canonicalize_oqo(parse_core(text)).to_dict() == canonicalize_oqo(oqo).to_dict()


# --- a corpus in the sentence, so the order survives ------------------------------------

@pytest.mark.parametrize("text,corpus", [
    ("get works (all corpora) with kelp in the title, most cited first", "all"),
    ("get works (all corpora) about kelp", "all"),
    ("get the count of works (all corpora) about kelp by year", "all"),
    ("get works (expansion corpus) since 2020 about kelp", "expansion"),
    ("get articles (all corpora) about kelp", "all"),
])
def test_a_corpus_reads_in_the_sentence(text, corpus):
    oqo = parse_core(text)
    assert oqo.corpus == corpus
    assert render_core(oqo) == text


def test_the_corpus_aliases_read():
    assert parse_core("get works (all) about kelp").corpus == "all"
    assert parse_core("get works (xpac) about kelp").corpus == "expansion"
    with pytest.raises(Exception):
        parse_core("get works (all corpora) about kelp. Only authors with at least 5 works (xpac) about kelp.")


def test_a_corpus_url_keeps_its_order():
    # `/works?filter=title.search:kelp&include_xpac=true&sort=cited_by_count:desc` echoed
    # `get works (all corpora) where title has (kelp)`, the order gone
    oqo = OQO.from_dict({"get_rows": "works", "corpus": "all",
                         "filter_rows": [{"column_id": "title.search", "value": "kelp", "operator": "has"}],
                         "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}]})
    assert render_core(oqo) == "get works (all corpora) with kelp in the title, most cited first"
