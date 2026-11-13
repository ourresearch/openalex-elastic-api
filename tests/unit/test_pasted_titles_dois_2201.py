"""oxjob #2201: pasted titles and DOIs.

1. A works search of several words that is not Boolean is pasted text: a starred title
   ("... Low Vertebral Bone Mass*"), a Markdown reference ("*On Bullshit*"), `A*`, mojibake
   (`Fran?ois`). Before, the stemmed doors answered HTTP 400 to about 9K such searches a day.
   Deliberate wildcards (one word, short searches, Boolean, quoted phrases) keep today's reading.
2. A lone `,` `×` `°` `=` in a Boolean or quoted search is not a keyword phrase: the keywords
   index lists symbols as synonyms, so `"climate change", "public health"` matched nothing.
3. /works/doi:<doi> and filter=doi: find a DOI pasted with a trailing `.` `,` `;`, as typed first.
No ES: the keyword lookup is stubbed and the lookups' backends answer 'not found'.
"""
import json
from unittest import mock

import pytest
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from core.filter import handle_or_query
from core.search_punctuation import pasted_door, wildcard_chars_as_punctuation
from core.shared_view import build_search_value_query
from ids.utils import doi_without_trailing_punctuation
from works.fields import fields_dict

VITAMIN_D = "Subclinical Vitamin D Deficiency in Postmenopausal Women with Low Vertebral Bone Mass*"


@pytest.fixture(autouse=True)
def no_keyword_lookup(monkeypatch):
    import core.keyword_search as ks
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: [] for s in spans})
    ks.keyword_record.cache_clear()
    yield
    ks.keyword_record.cache_clear()


STEMMED = [
    (VITAMIN_D, VITAMIN_D[:-1]),
    ("THE STRUCTURE OF MICROTUBULES*", "THE STRUCTURE OF MICROTUBULES"),
    ("UAV Maritime Search and Rescue Based on Improved A* and RCPP Algorithms",
     "UAV Maritime Search and Rescue Based on Improved A and RCPP Algorithms"),
    ("Ich unterstütze dich bei neurologischen Patient*innen", "Ich unterstütze dich bei neurologischen Patient innen"),
    ("A note on unitary operators in C*-algebras", "A note on unitary operators in C-algebras"),
    ("The optimality of A* revisited", "The optimality of A revisited"),
    ("O*NET Interest Profiler Short Form", "O NET Interest Profiler Short Form"),
    ("selfless C*-algebras", "selfless C-algebras"),
    # Markdown emphasis, at any length
    ("*On Bullshit*", "On Bullshit"),
    ("*Informe anual de desempeño 2020*", "Informe anual de desempeño 2020"),
    ("Trommel, W. (2018). *Veerkrachtig bestuur*. Amsterdam: Boom.", "Trommel, W. (2018). Veerkrachtig bestuur. Amsterdam: Boom."),
    ("| **Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
     "| Mamba: Linear-Time Sequence Modeling with Selective State Spaces"),
    ("Estrategias de comunicación en negociaciones**.", "Estrategias de comunicación en negociaciones."),
    ("J. Huang, T. Liu*, ACS Appl. Nano Mater. 2025, 8, 764.", "J. Huang, T. Liu, ACS Appl. Nano Mater. 2025, 8, 764."),
    ("Predicting*the*potential*health impact*of*a*sugary*drink*tax", "Predicting the potential health impact of a sugary drink tax"),
    # an upper-case title's AND / OR / NOT are words
    ("RISING OCCUPATIONAL AND INDUSTRY MOBILITY IN THE UNITED STATES: 1968–97*",
     "RISING OCCUPATIONAL AND INDUSTRY MOBILITY IN THE UNITED STATES: 1968–97"),
    ("GOVERNANCE AND ILLICIT FINANCIAL FLOWS*", "GOVERNANCE AND ILLICIT FINANCIAL FLOWS"),
    # mojibake: `?` inside or leading a word
    ("Fran?ois Mitterrand et la Cinqui?me R?publique", "Fran ois Mitterrand et la Cinqui me R publique"),
    ("?Qu? es la ciencia abierta", "Qu es la ciencia abierta"),
    ("some ?cycle", "some cycle"),
    # a truncation among many words reads as the word (stemming finds its plurals)
    ("large-scale language model* radiological report generation", "large-scale language model radiological report generation"),
]


@pytest.mark.parametrize("given, expected", STEMMED)
def test_pasted_text_on_the_stemmed_door(given, expected):
    out = wildcard_chars_as_punctuation(given, pasted="stemmed")
    assert out == expected
    assert wildcard_chars_as_punctuation(out, pasted="stemmed") == out  # idempotent


@pytest.mark.parametrize("terms", [
    "hemosta*", "wom?n", "基于改进A*算法的自主导航水上垃圾收集船",  # one word
    "machin* learning", "pest* fruit quality", "Lake Kariba bathymetr*", "atypic* antipsychotic*",  # short
    "wom?n health", "HLA-DRB1*15 meningococcal",
    "child* obes* school* interven*", "nurs* educat* simulat* train* program",  # a third or more truncated
    "parent* OR mother*", "nematode* AND litter", "depression AND suicid* AND sleep AND predict*",  # Boolean
    "(India OR Indian OR Himalaya*) AND (plant OR orchid* OR timber)", "repurpos* NOT cancer",
    '"smart phone*"~3', '"art therap*"', '"citizen develop*"', '"weighted A*"',  # quoted phrases
    '"UAV Maritime Search and Rescue Based on Improved A* and RCPP Algorithms"',
])
@pytest.mark.parametrize("door", ["stemmed", "exact"])
def test_a_deliberate_wildcard_reads_as_before(terms, door):
    assert wildcard_chars_as_punctuation(terms, pasted=door) == wildcard_chars_as_punctuation(terms)


@pytest.mark.parametrize("given, expected", [
    # a `*` no wildcard rule accepts is punctuation on the exact door too
    ("UAV Maritime Search and Rescue Based on Improved A* and RCPP", "UAV Maritime Search and Rescue Based on Improved A and RCPP"),
    ("*On Bullshit*", "On Bullshit*"),  # the closing `*` is a prefix wildcard there, and still finds the title
    ("**Fractal Information Encoding (FIE)**", "Fractal Information Encoding (FIE)"),
    # a truncation and a `?` inside a word stay wildcards on the exact door
    (VITAMIN_D, VITAMIN_D),
    ("long term outcomes after bariatric surg*", "long term outcomes after bariatric surg*"),
    ("wom?n health in rural Kenya", "wom?n health in rural Kenya"),
])
def test_pasted_text_on_the_exact_door(given, expected):
    out = wildcard_chars_as_punctuation(given, pasted="exact")
    assert out == expected
    assert wildcard_chars_as_punctuation(out, pasted="exact") == out


@pytest.mark.parametrize("terms", [t for t, _ in STEMMED] + ["machin* learning", "parent* OR mother*"])
def test_without_a_door_nothing_changes(terms):
    # OQL and every non-works entity keep oxjob #1327's reading
    before = wildcard_chars_as_punctuation(terms)
    assert wildcard_chars_as_punctuation(terms, pasted=None) == before
    assert wildcard_chars_as_punctuation(terms, pasted=pasted_door("display_name.search", "sources")) == before


@pytest.mark.parametrize("field, entity, want", [
    ("title.search", "works", "stemmed"), ("fulltext.search", "works-v39", "stemmed"),
    ("title_abstract_keywords.search", "works", "stemmed"), ("title.search.exact", "works", "exact"),
    ("title_and_abstract.search.exact", "works", "exact"), ("raw_affiliation_strings.search", "works", None),
    ("semantic.search", "works", None), ("display_name.search", "authors", None), ("title.search", None, None),
])
def test_pasted_door(field, entity, want):
    assert pasted_door(field, entity) == want


def _param(value, search_type="default", scope=None, index="works-v39"):
    return build_search_value_query(index, value, scope, search_type).to_dict()


def _filter(key, value):
    return handle_or_query(fields_dict[key], {}, Search(), value, sample=None).to_dict()


@pytest.mark.parametrize("given, expected", STEMMED[:6] + STEMMED[8:11])
def test_the_search_param_builds_the_query_of_the_clean_text(given, expected):
    assert _param(given) == _param(expected)
    assert _param(given, scope="title") == _param(expected, scope="title")


@pytest.mark.parametrize("key", ["title.search", "title_and_abstract.search", "title_abstract_keywords.search"])
@pytest.mark.parametrize("given, expected", [STEMMED[0], STEMMED[2], STEMMED[8]])
def test_the_filter_doors_build_the_query_of_the_clean_text(key, given, expected):
    assert _filter(key, given) == _filter(key, expected)


@pytest.mark.parametrize("terms", ["machin* learning", "parent* OR mother*", "hemosta*", "pest* fruit quality", "wom?n health"])
def test_a_deliberate_wildcard_still_gets_the_exact_search_advice(terms):
    with pytest.raises(APIQueryParamsError, match="exact"):
        _param(terms)
    with pytest.raises(APIQueryParamsError, match="title.search.exact"):
        _filter("title.search", terms)


def test_other_entities_are_untouched():
    # sources search keeps its own reading of `Oncology*Biology*Physics` (oxjob #1327)
    name = "International Journal of Radiation Oncology*Biology*Physics"
    assert _param(name, index="sources-v3") != _param(name.replace("*", " "), index="sources-v3")


# --- 2. symbols are not keyword phrases ---

@pytest.mark.parametrize("q, texts", [
    ('"climate change", "public health"', ["climate change", "public health"]),
    ("tomato AND yield , nitrogen", ["tomato", "yield", "nitrogen"]),
    ("heat AND 40 ° C", ["heat", "40", "C"]),
    ("(MALUS × DOMESTICA) AND apple", ["MALUS", "DOMESTICA", "apple"]),
    ('"a = b" AND x - y', ["a = b", "x", "y"]),
    ('"," OR "×" OR dog', ["dog"]),
])
def test_a_leaf_with_no_letter_or_digit_is_not_looked_up(q, texts):
    from core.keyword_search import query_string_leaves
    assert [t for _, _, t in query_string_leaves(q)] == texts


def test_a_comma_between_quoted_phrases_adds_no_keyword_clause(monkeypatch):
    import core.keyword_search as ks
    # the keywords index: 'comma' has `,` as a synonym
    monkeypatch.setattr(ks, "lookup", lambda spans: {s: (["https://openalex.org/keywords/comma"] if s == "," else [])
                                                     for s in spans})
    ks.keyword_record.cache_clear()
    body = json.dumps(_param('"climate change", "public health"'))
    assert "keywords/comma" not in body


# --- 3. DOIs with trailing punctuation ---

@pytest.mark.parametrize("doi, want", [
    ("10.1103/physrevlett.104.211103.", "10.1103/physrevlett.104.211103"),
    ("10.1038/s41598-024-79743-y,", "10.1038/s41598-024-79743-y"),
    ("10.1371/journal.pone.0139778;", "10.1371/journal.pone.0139778"),
    ("10.1038/s41467-024-47621-w**", "10.1038/s41467-024-47621-w"),
    ("10.1038/nature12373).", "10.1038/nature12373"),
    ("10.1038/nature12373", None), ("10.1016/0021-9991(90)90007-n", None), ("", None), (None, None),
])
def test_doi_without_trailing_punctuation(doi, want):
    assert doi_without_trailing_punctuation(doi) == want


@pytest.fixture
def app_client(monkeypatch):
    for k, v in {"REDSHIFT_SERVERLESS_URL": "postgresql://u:p@localhost:5432/db",
                 "REDIS_DO_URL": "redis://localhost:6379", "REDISCLOUD_URL": "redis://localhost:6379",
                 "USERS_DB_URL": "postgresql://u:p@localhost:5432/db",
                 "DATABASE_URL": "postgresql://u:p@localhost:5432/db", "JWT_SECRET_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    from app import create_app
    return create_app("tests.settings").test_client()


def _lookup(app_client, path, found=()):
    """(response, the DOIs Lakebase was asked for, in order); Lakebase holds only the DOIs in `found`."""
    asked = []

    def fake_ext(ext_id):
        asked.append(ext_id)
        return {"id": "https://openalex.org/W1", "ids": {"openalex": "https://openalex.org/W1", "doi": ext_id},
                "doi": ext_id} if ext_id in found else None

    with mock.patch("elasticsearch_dsl.Search.execute", lambda self: []), \
            mock.patch("works.lakebase.should_route", return_value=True), \
            mock.patch("works.lakebase.get_work_doc_by_ext_id", fake_ext), \
            mock.patch("ids.views.redirect_if_merged", return_value=None):
        r = app_client.get(path, follow_redirects=True)
    return r, asked


@pytest.mark.parametrize("path", [
    "/works/doi:10.1103/physrevlett.104.211103.", "/works/https://doi.org/10.1103/PhysRevLett.104.211103,",
    "/works/10.1103/physrevlett.104.211103;", "/works/DOI:10.1103/physrevlett.104.211103).",
])
def test_a_doi_lookup_retries_without_trailing_punctuation(app_client, path):
    full = "https://doi.org/10.1103/physrevlett.104.211103"
    r, asked = _lookup(app_client, path, found={full})
    assert r.status_code == 200
    assert asked[-1] == full and len(asked) == 2 and asked[0].startswith(full)  # as typed first


def test_a_real_doi_ending_in_a_dot_answers_as_typed(app_client):
    full = "https://doi.org/10.1234/abc."
    r, asked = _lookup(app_client, "/works/doi:10.1234/abc.", found={full, full[:-1]})
    assert r.status_code == 200 and asked == [full]


def test_an_unknown_doi_is_still_a_404(app_client):
    r, asked = _lookup(app_client, "/works/doi:10.1234/nothing.")
    assert r.status_code == 404
    assert asked == ["https://doi.org/10.1234/nothing.", "https://doi.org/10.1234/nothing"]
    r, asked = _lookup(app_client, "/works/doi:10.1234/nothing")
    assert r.status_code == 404 and asked == ["https://doi.org/10.1234/nothing"]


def _filter_body(key, value):
    from core.filter import filter_records
    return json.dumps(filter_records(fields_dict, [{key: value}], Search()).to_dict(), sort_keys=True)


@pytest.mark.parametrize("value", ["10.1038/nature12373.", "https://doi.org/10.1038/nature12373,", "doi:10.1038/NATURE12373;"])
def test_the_doi_filter_also_matches_without_trailing_punctuation(value):
    body = _filter_body("doi", value)
    assert '"https://doi.org/10.1038/nature12373"' in body       # stripped
    assert '"https://doi.org/10.1038/nature12373%s"' % value[-1] in body  # as typed


def test_the_doi_filter_without_trailing_punctuation_is_unchanged():
    assert _filter_body("doi", "10.1038/nature12373").count("nature12373") == 3  # short, full, a location's


def test_the_doi_or_list_also_matches_without_trailing_punctuation():
    body = _filter_body("doi", "10.1038/nature12373.|10.1/x")
    assert '"https://doi.org/10.1038/nature12373"' in body and '"https://doi.org/10.1038/nature12373."' in body
