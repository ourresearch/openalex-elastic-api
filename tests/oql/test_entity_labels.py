"""Entity values as `<display name> [<ID>]` and bare single values (oxjob #1555, Jason
2026-10-06). The ID decides; the name is a label the parser never reads. One test per
way it could break (the list Jason reviewed), plus the old forms."""
import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import parse, render
from query_translation.oqo_canonicalizer import canonicalize_oqo

NAMES = {
    "I1": "Texas A&M University and Health Science Center",
    "I8961855": "Universidad Nacional Autónoma de México (UNAM)",
    "F4320334764": "Japan Science and Technology Agency (JST)",
    "T10032": "Marine and coastal ecosystems",
    "S1": 'The "Journal"; of [Things]',
    "S2": "Notes and Queries",
    "A1": "and year is 2020",
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
    q = f"get works where {column} is {ident} and year > 2020"
    echo = _echo(q)
    assert f"[{ident}]" in echo
    assert _canon(echo) == _canon(q)


# 1-3. and / or / not, parentheses, commas inside a name: everything up to the ID
@pytest.mark.parametrize("q,want", [
    ("get works where institution is Texas A&M University and Health Science Center [I1] "
     "and year > 2020", ["I1", 2020]),
    ("get works where institution is Universidad Nacional Autónoma de México (UNAM) "
     "[I8961855]", ["I8961855"]),
    ("get works where funder is Japan Science and Technology Agency (JST) [F4320334764]",
     ["F4320334764"]),
    ("get works where institution is University of California, Berkeley [I95457486]",
     ["I95457486"]),
])
def test_a_name_is_never_parsed(q, want):
    assert sorted(map(str, _values(q))) == sorted(map(str, want))


# 3-5. what the renderer tidies or quotes (labels are ignored, so this is free)
def test_brackets_quotes_and_semicolons_in_a_name():
    echo = _echo("get works where source is S1")
    assert echo == "get works where source is \"The 'Journal'; of (Things)\" [S1]"


def test_a_name_that_reads_like_a_condition_is_quoted():
    assert _echo("get works where author is A1") == \
        'get works where author is "and year is 2020" [A1]'


def test_a_name_starting_with_not_is_quoted_only_if_needed():
    assert _echo("get works where source is S2") == \
        "get works where source is Notes and Queries [S2]"


# 6. a typed name with no ID fails where the next condition starts
def test_a_name_without_its_id_does_not_swallow_the_query():
    with pytest.raises(OQLError) as e:
        parse("get works where institution is Massachusetts Institute of Technology "
              "and year > 2020 and institution is Harvard University [I136199984]")
    assert e.value.code == "OQL_MISSING_ENTITY_ID"
    assert "Massachusetts Institute of Technology" in e.value.message


# 7. two names with one ID: the ID runs, and the echo shows its real name
def test_two_names_one_id_runs_as_the_id():
    q = "get works where institution is MIT or Stanford [I97018004]"
    assert _values(q) == ["I97018004"]
    assert _echo(q) == "get works where institution is Stanford University [I97018004]"


# 8. a changed name changes nothing
def test_the_label_never_matters():
    assert _canon("get works where institution is Old Name [I63966007]") == \
        _canon("get works where institution is Massachusetts Institute of Technology "
               "[I63966007]")


# 9. an ID of the wrong kind
def test_wrong_kind_of_id():
    with pytest.raises(OQLError) as e:
        parse("get works where institution is Harvard [A5066175077]")
    assert e.value.code == "OQL_WRONG_ENTITY_ID"


# 10. the ID alone, bracketed or not, and the old ID-first form
@pytest.mark.parametrize("q", [
    "get works where institution is [I63966007]",
    "get works where institution is I63966007",
    "get works where institution is (I63966007 [MIT])",
    "get works where institution is (I63966007)",
])
def test_old_and_bare_forms(q):
    assert _values(q) == ["I63966007"]
    assert _echo(q) == ("get works where institution is Massachusetts Institute of "
                        "Technology [I63966007]")


# 11. line breaks never split a name in a way that changes the query
def test_multi_line_echo_round_trips_with_names():
    q = ("get works where institution is I1 and topic is T10032 and funder is F4320334764 "
         "and year >= 2020 and type is article; then group those works by institution "
         "in (I1, I63966007); then calculate count")
    echo = _echo(q)
    assert "\n" in echo
    assert _canon(echo) == _canon(q)


# lists keep one pair of parentheses; single values lose theirs
@pytest.mark.parametrize("q,echo", [
    ("works where institution is (I63966007 or I97018004)",
     "get works where institution is (Massachusetts Institute of Technology [I63966007] "
     "or Stanford University [I97018004])"),
    ("works where year >= (2020) and type is not (review) and open access is (true)",
     "get works where open access is true and year >= 2020 and type is not review"),
    ("works where FWCI > (-1)", "get works where FWCI > -1"),
    ("works where title-abstract has (wind power)",
     "get works where title-abstract has (wind power)"),
])
def test_value_forms(q, echo):
    assert _echo(q) == echo
    assert _canon(echo) == _canon(q)
