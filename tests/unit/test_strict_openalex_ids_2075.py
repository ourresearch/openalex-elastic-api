"""An OpenAlex ID filter value with text after the ID is a 400, not the ID alone (oxjob #2075).

`authorships.author.id:A5031124015~editor` and `.../A5031124015/editor` answered every work of A5031124015, and
`corresponding_author_ids:A5031124015/editor` every work he is corresponding author on: the id parser took the first
ID it found anywhere in the value. Filters now take a value only when it is one ID and nothing else (short form in any
case, or its URL). Entity paths keep the old reading, so /works/W123/anything still finds W123. No ES: the merge-index
lookup is faked.

    PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_strict_openalex_ids_2075.py --noconftest -q
"""
import json

import pytest
from elasticsearch_dsl import Search

import core.merged_ids as merged_ids
from authors.fields import fields_dict as authors_fields
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.utils import get_full_openalex_id, normalize_openalex_id
from links.views import work_id
from tests.unit.test_merged_ids import FakeES, _fresh_state
from works.fields import fields_dict as works_fields

AUTHOR = "A5031124015"
AUTHOR_URL = "https://openalex.org/" + AUTHOR


@pytest.fixture(autouse=True)
def es(monkeypatch):
    _fresh_state(monkeypatch)  # the fake merge index: A5107411446 was merged into A5107863564
    monkeypatch.setattr(merged_ids, "get_connection", lambda *a, **k: FakeES())


def _body(key, value, fields=works_fields):
    return json.dumps(filter_records(fields, [{key: value}], Search()).to_dict())


def _error(key, value, fields=works_fields):
    with pytest.raises(APIQueryParamsError) as err:
        _body(key, value, fields)
    return str(err.value)


# ---------- the parser ----------

ACCEPTED = [
    "A5031124015", "a5031124015", " A5031124015 ", "A5031124015/",
    "https://openalex.org/A5031124015", "http://openalex.org/A5031124015", "openalex.org/A5031124015",
    "HTTPS://OPENALEX.ORG/a5031124015", "https://openalex.org/authors/A5031124015",
    "https://api.openalex.org/authors/A5031124015", "openalex:A5031124015", "authors/A5031124015",
]
REJECTED = [
    "A5031124015~editor", "A5031124015/editor", "https://openalex.org/A5031124015/editor", "A5031124015editor",
    "A5031124015N", "xA5031124015", "A5031124015A5031124015", "https://openalex.org.evil/A5031124015",
    "editor/A5031124015", "https://openalex.org/editor/A5031124015",
]


@pytest.mark.parametrize("value", ACCEPTED)
def test_strict_reads_one_id_in_any_accepted_form(value):
    assert normalize_openalex_id(value, strict=True) == AUTHOR
    assert get_full_openalex_id(value, strict=True) == AUTHOR_URL


@pytest.mark.parametrize("value", REJECTED + ["", None, "fff", "A1"])
def test_strict_refuses_anything_more_or_less_than_one_id(value):
    assert normalize_openalex_id(value, strict=True) is None
    assert get_full_openalex_id(value, strict=True) is None


@pytest.mark.parametrize("value", ["A5031124015/editor", "A5031124015~editor", "/authors/A5031124015/works"])
def test_lenient_reading_is_unchanged_for_entity_paths(value):
    assert normalize_openalex_id(value) == AUTHOR


# ---------- filters: the rejects ----------

@pytest.mark.parametrize("key, value, bad", [
    ("authorships.author.id", "A5031124015~editor", "A5031124015~editor"),
    ("authorships.author.id", "A5031124015/editor", "A5031124015/editor"),
    ("authorships.author.id", "https://openalex.org/A5031124015/editor", "https://openalex.org/A5031124015/editor"),
    ("author.id", "A5031124015~editor", "A5031124015~editor"),
    ("corresponding_author_ids", "A5031124015/editor", "A5031124015/editor"),
    ("authorships.author.id", "A5031124015|A5031124015~editor", "A5031124015~editor"),   # one bad OR operand
    ("authorships.author.id", "!A5031124015~editor", "A5031124015~editor"),             # negated
    ("authorships.author.id", "!A1234567|A5031124015~editor", "A5031124015~editor"),    # negated OR
    ("authorships.author.id", "A1234567 A5031124015~editor", "A5031124015~editor"),     # + (AND)
    ("cites", "W1979680610~W2943645473", "W1979680610~W2943645473"),
    ("cited_by", "W2741809807/editor", "W2741809807/editor"),
    ("authorships.institutions.id", "I136199984~x", "I136199984~x"),
    ("authorships.institutions.id", "!I136199984~x", "I136199984~x"),
    ("primary_location.source.id", "S137773608x", "S137773608x"),
    ("lineage", "W2741809807/x", "W2741809807/x"),
    ("openalex", "W2741809807~x", "W2741809807~x"),
])
def test_an_id_with_text_after_it_is_a_400_that_names_the_value(key, value, bad):
    message = _error(key, value)
    assert f"'{bad}' is not a valid OpenAlex" in message
    assert "Give the ID alone" in message


def test_the_message_names_the_kind_of_id():
    assert _error("authorships.author.id", "A5031124015~editor").startswith(
        "'A5031124015~editor' is not a valid OpenAlex author ID. Give the ID alone, like A5031124015 or "
        "https://openalex.org/A5031124015")


def test_topic_id_term_filter_on_authors_refuses_text_after_the_id():
    assert "'T10017~x' is not a valid OpenAlex topic ID" in _error("topics.id", "T10017~x", authors_fields)


def test_a_value_with_no_id_keeps_its_old_message():
    assert _error("concepts.id", "fff") == "'fff' is not a valid OpenAlex ID."


def test_links_origin_takes_one_work_id_alone():
    assert work_id("W2741809807", "origin") == "W2741809807"
    assert work_id("https://openalex.org/W2741809807", "origin") == "W2741809807"
    with pytest.raises(APIQueryParamsError):
        work_id("W2741809807~x", "origin")


# ---------- filters: what keeps working ----------

@pytest.mark.parametrize("value", [v for v in ACCEPTED if v == v.strip()])  # a space in a filter value means AND
def test_author_filter_reads_every_accepted_form(value):
    body = _body("authorships.author.id", value)
    assert f'"{AUTHOR_URL}"' in body


def test_or_negation_and_and_still_work():
    assert body_has(_body("authorships.author.id", "A5031124015|a1234567"), AUTHOR_URL, "https://openalex.org/A1234567")
    assert '"must_not"' in _body("authorships.author.id", "!A5031124015")
    assert '"must_not"' in _body("authorships.author.id", "!A5031124015|A1234567")
    assert body_has(_body("authorships.author.id", "A5031124015 A1234567"), AUTHOR_URL, "https://openalex.org/A1234567")
    assert body_has(_body("corresponding_author_ids", AUTHOR), AUTHOR_URL)


def test_negated_institution_filter_still_reads_the_id():
    # this branch used to validate the value with its leading `!` (fine only while parsing was lenient)
    body = _body("authorships.institutions.id", "!I136199984")
    assert '"must_not"' in body and "https://openalex.org/I136199984" in body


def test_merged_author_still_matches_its_winner():
    body = _body("authorships.author.id", "a5107411446")
    assert body_has(body, "https://openalex.org/A5107411446", "https://openalex.org/A5107863564")


def test_null_and_not_null_untouched():
    assert '"exists"' in _body("authorships.author.id", "null")
    assert '"exists"' in _body("authorships.author.id", "!null")


def test_topic_id_term_filter_on_authors_still_reads_short_ids_and_urls():
    for value in ("T10017", "t10017", "https://openalex.org/T10017", "https://openalex.org/topics/T10017"):
        assert "https://openalex.org/T10017" in _body("topics.id", value, authors_fields)


def body_has(body, *needles):
    return all(f'"{n}"' in body for n in needles)


# ---------- the other filter paths that read OpenAlex IDs ----------

def test_url_term_filters_refuse_text_after_the_id_and_read_any_url_form():
    from awards.fields import fields_dict as awards_fields
    key = "authorships.affiliations.institution_ids"
    assert "'I136199984~x' is not a valid OpenAlex institution ID" in _error(key, "I136199984~x")
    for value in ("I136199984", "i136199984", "https://openalex.org/I136199984", "http://openalex.org/I136199984"):
        assert "https://openalex.org/I136199984" in _body(key, value)
    assert "'G2966666733/x' is not a valid OpenAlex award ID" in _error("id", "G2966666733/x", awards_fields)
    assert "https://openalex.org/G2966666733" in _body("id", "g2966666733", awards_fields)


def test_semantic_search_filters_refuse_text_after_the_id():
    from core.vector_index import _build_single_filter
    with pytest.raises(APIQueryParamsError, match="'A5031124015~editor' is not a valid OpenAlex author ID"):
        _build_single_filter("authorships.author.id", "authorships.author.id", "A5031124015~editor")
    with pytest.raises(APIQueryParamsError):
        _build_single_filter("authorships.author.id", "authorships.author.id", "A1234567|A5031124015/editor")
    assert _build_single_filter("authorships.author.id", "f", "a5031124015") == {"term": {"f": AUTHOR_URL}}
    assert _build_single_filter("authorships.author.id", "f", f"{AUTHOR}|A1234567") == {
        "terms": {"f": [AUTHOR_URL, "https://openalex.org/A1234567"]}}
