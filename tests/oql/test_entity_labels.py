"""Entity values as Markdown links, `[display name](ID)`, and bare single values
(oxjob #1555, Jason 2026-10-06 and 2026-10-08). The ID decides; the name is a label the
parser never reads; the name is optional. One test per way it could break, plus the
old and permissive forms."""
import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse, render
from query_translation.oqo_canonicalizer import canonicalize_oqo
from query_translation.validator import validate_oqo

NAMES = {
    "I1": "Texas A&M University and Health Science Center",
    "I8961855": "Universidad Nacional Autónoma de México (UNAM)",
    "F4320334764": "Japan Science and Technology Agency (JST)",
    "T10032": "Marine and coastal ecosystems",
    "S1": 'The "Journal"; of [Things]',
    "S2": "Notes and Queries",
    "A1": "and published in 2020",
    "I63966007": "Massachusetts Institute of Technology",
    "I97018004": "Stanford University",
}


def resolver(value, column_id):
    return NAMES.get(str(value))


def _canon(q):
    return canonicalize_oqo(parse(q)).to_dict()


def _echo(q):
    return render(canonicalize_oqo(parse(q)), resolver=resolver, style="pipeline")


def _values(q):
    return [f["value"] for f in _canon(q)["filter_rows"]]


@pytest.mark.parametrize("ident,column", [
    ("I1", "institution"), ("I8961855", "institution"), ("F4320334764", "funder"),
    ("T10032", "topic"), ("S1", "source"), ("S2", "source"), ("A1", "author"),
])
def test_every_name_round_trips(ident, column):
    q = f"get works where {column} is {ident} and published after 2020"
    echo = _echo(q)
    assert f"]({ident})" in echo
    assert _canon(echo) == _canon(q)


# and / or / not, parentheses, commas, quotes, semicolons inside a name: it's a label
@pytest.mark.parametrize("q,want", [
    ("get works where institution is [Texas A&M University and Health Science Center](I1) "
     "and published after 2020", ["I1", 2020]),
    ("get works where institution is [Universidad Nacional Autónoma de México (UNAM)]"
     "(I8961855)", ["I8961855"]),
    ("get works where funder is [Japan Science and Technology Agency (JST)](F4320334764)",
     ["F4320334764"]),
    ("get works where institution is [University of California, Berkeley](I95457486)",
     ["I95457486"]),
    ('get works where source is [The "Journal"; of (Things)](S1) and published after 2020', ["S1", 2020]),
    ("get works where author is [and published in 2020](A1)", ["A1"]),
])
def test_a_name_is_never_parsed(q, want):
    assert sorted(map(str, _values(q))) == sorted(map(str, want))


def test_brackets_in_a_name_become_parentheses():
    assert _echo("get works where source is S1") ==\
        "get works where source is [The \"Journal\"; of (Things)](S1)"


def test_a_name_without_its_id_is_an_error():
    for q in ("get works where institution is [Massachusetts Institute of Technology]",
              "get works where institution is [Massachusetts Institute of Technology] "
              "and published after 2020"):
        with pytest.raises(OQLError) as e:
            parse(q)
        assert e.value.code == "OQL_MISSING_ENTITY_ID"


def test_a_link_holds_one_id():
    with pytest.raises(OQLError) as e:
        parse("get works where institution is [MIT](I63966007 I97018004)")
    assert e.value.code == "OQL_BAD_ENTITY_LINK"


# two names with one ID: the ID runs, and the echo shows its real name
def test_two_names_one_id_runs_as_the_id():
    q = "get works where institution is [MIT or Stanford](I97018004)"
    assert _values(q) == ["I97018004"]
    assert _echo(q) == "get works where institution is [Stanford University](I97018004)"


def test_the_name_never_matters():
    assert _canon("get works where institution is [Old Name](I63966007)") ==\
        _canon("get works where institution is [Massachusetts Institute of Technology]"
               "(I63966007)")


def test_an_id_of_the_wrong_kind_is_a_validation_error():
    r = validate_oqo(canonicalize_oqo(parse("get works where institution is "
                                            "[Harvard University](A5066175077)")))
    assert not r.valid


# the name is optional; every older form and the URL forms still read the same
@pytest.mark.parametrize("q", [
    "get works where institution is (I63966007)",
    "get works where institution is I63966007",
    "get works where institution is i63966007",
    "get works where institution is (I63966007 [MIT])",
    "get works where institution is [I63966007]",
    "get works where institution is [MIT](I63966007)",
    "get works where institution is [MIT] (I63966007)",
    "get works where institution is [MIT](https://openalex.org/I63966007)",
    "get works where institution is [MIT](openalex.org/institutions/i63966007)",
    "get works where institution is http://api.openalex.org/institutions/I63966007",
])
def test_old_bare_and_url_forms(q):
    assert _values(q) == ["I63966007"]
    assert _echo(q) == ("get works where institution is [Massachusetts Institute of "
                        "Technology](I63966007)")


def test_multi_line_echo_round_trips_with_names():
    q = ("get works where institution is I1 and topic is T10032 and funder is F4320334764 "
         "and published since 2020 and type is article; then group those works by institution "
         "in (I1, I63966007); then summarize using count")
    echo = _echo(q)
    assert "\n" in echo
    assert _canon(echo) == _canon(q)


# every entity is a link (closed vocabularies too); lists keep one pair of
# parentheses; other single values lose theirs
@pytest.mark.parametrize("q,echo", [
    ("works where institution is (I63966007 or I97018004)",
     "get works where institution is ([Massachusetts Institute of Technology](I63966007) "
     "or [Stanford University](I97018004))"),
    ("works where year >= (2020) and type is not (review) and open access is (true)",
     "get works where it's open access and published since 2020 and type is not [review](review)"),
    ("works where country is KE and language is fr",
     "get works where country is [Kenya](KE) and language is [French](fr)"),
    ("works where institution is I999", "get works where institution is (I999)"),
    ("works where FWCI > (-1)", "get works where FWCI > -1"),
    ("works where title-abstract has (wind power)",
     "get works where title-abstract has (wind power)"),
])
def test_value_forms(q, echo):
    assert " ".join(_echo(q).split()) == echo
    assert _canon(echo) == _canon(q)
