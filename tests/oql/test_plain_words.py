"""Plain words inside an OQL statement (oxjob #1597): the parser-side detection behind
`/validate?plain_words=1`. Cases from the job's case set (work/plain_words_cases.jsonl)."""
import pytest

from query_translation import oql_core as C
from query_translation.editor_views import _add_plain_words
from query_translation.oql_plain_words import find


def plain(q):
    r = find(q)
    assert r and r["kind"] == "plain", r
    assert q[r["start"]:r["end"]] == r["text"]
    return r["text"], r["rest"]


@pytest.mark.parametrize("q", [
    "get works about kelp since 2020, most cited first",
    "get the count of works about kelp funded by [National Science Foundation](F4320306076) by country",
    "get open access articles about (coral reefs) from [Kenya](KE) since 2015",
    "",
])
def test_oql_that_reads_has_no_plain_words(q):
    assert find(q) is None


@pytest.mark.parametrize("q", [
    "get works about kelp since",               # an OQL word being typed at the end
    "get works about kelp since 2020, most cit",
])
def test_oql_being_typed_is_not_plain_words(q):
    assert find(q) is None


@pytest.mark.parametrize("q,word,fix", [
    ("get works about kelp fundd by [National Science Foundation](F4320306076)", "fundd", "funded"),
    ("get works about kelp snce 2020", "snce", "since"),
    ("get works about kelp since 2020, most cted first", "cted", "cited"),
    ("get artciles about kelp since 2020", "artciles", "articles"),
])
def test_a_typo_gets_a_fix_not_the_model(q, word, fix):
    r = find(q)
    assert r["kind"] == "typo" and r["word"] == word and r["fix"] == fix
    assert q[r["start"]:r["end"]] == word


@pytest.mark.parametrize("q,text,rest", [
    ("get works about kelp since 2020 but only the open access ones",
     "but only the open access ones", "get works about kelp since 2020"),
    # rightmost and no stolen values: `from canada`, not `kelp from` (which leaves `about canada`)
    ("get works about kelp from canada since 2020", "from canada", "get works about kelp since 2020"),
    ("get works about kelp written by people at stanford since 2020, most cited first",
     "written by people at stanford", "get works about kelp since 2020, most cited first"),
    ("get [University of Oxford](I40120149)'s works about (malaria AND vaccine) only 2022 onwards, newest first",
     "only 2022 onwards",
     "get [University of Oxford](I40120149)'s works about (malaria AND vaccine), newest first"),
    ("get works about \"ROPME Sea Area\" only research articles",
     "only research articles", "get works about \"ROPME Sea Area\""),
    # the comma came with the plain words
    ("get the count of works about tb, only 2015 onward by institution in [Africa](Q15)",
     "only 2015 onward", "get the count of works about tb by institution in [Africa](Q15)"),
    # inside a list of links
    ("get the count of works since 2015 by institution in ([Indian Institute of Technology Bombay](I162827531), "
     "iit madras, [Indian Institute of Science Bangalore](I59270414))",
     "iit madras",
     "get the count of works since 2015 by institution in ([Indian Institute of Technology Bombay](I162827531), "
     "[Indian Institute of Science Bangalore](I59270414))"),
])
def test_plain_words_and_the_rest(q, text, rest):
    assert plain(q) == (text, rest)


def test_a_statement_that_isnt_oql_is_all_plain_words():
    assert plain("papers about kelp from chile in the last five years") == (
        "papers about kelp from chile in the last five years", None)


def test_a_list_of_links_refuses_other_words():
    # used to drop `iit madras` silently (loud, never silent)
    with pytest.raises(C.NotCore, match="iit madras"):
        C.parse_core("get the count of works by institution in ([Indian Institute of Technology Bombay]"
                     "(I162827531), iit madras)")
    C.parse_core("get the count of works by institution in ([Indian Institute of Technology Bombay]"
                 "(I162827531), [Indian Institute of Science Bangalore](I59270414))")


def test_validate_body_gains_plain_words_or_a_typo():
    def body():
        return {"valid": False, "diagnostics": [{"code": "OQL_PARSE_ERROR"}]}
    q = "get works about kelp since 2020 but only the open access ones"
    got = body()
    _add_plain_words(q, got)
    assert got["plain_words"] == {"start": 32, "end": len(q), "text": "but only the open access ones"}
    assert [(d["code"], d["severity"], d["start"], d["end"]) for d in got["diagnostics"]] == [
        ("OQL_PLAIN_WORDS", "info", 32, len(q))]
    typo = body()
    _add_plain_words("get works about kelp snce 2020", typo)
    assert typo["diagnostics"][0]["code"] == "OQL_TYPO"
    assert typo["diagnostics"][0]["replacement"] == "since"
    assert "plain_words" not in typo
    unchanged = body()
    _add_plain_words("get works about kelp since", unchanged)     # still typing
    assert unchanged == body()
