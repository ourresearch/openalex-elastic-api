"""Names everywhere a value names an entity (oxjob #1555, Jason 2026-10-08): co-author
and collaborator values, `get each ... in (...)` starts, collections; and named sets in
one pair of parentheses."""
import pytest

from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oql_renderer import make_engine_resolver
from query_translation.oqo_canonicalizer import canonicalize_oqo

NAMES = {
    "collections/col_abc123": "Climate topics", "collections/col_auth9": "Our lab",
    "authors/A5066175077": "Stephen Hawking", "authors/A1": "Jane Smith",
    "institutions/I63966007": "Massachusetts Institute of Technology",
    "institutions/I97018004": "Stanford University", "institutions/I99464096": "KU Leuven",
}


def _lookup(key):
    ns, short = key.split("/", 1)
    return NAMES.get(f"{ns}/{short}") or NAMES.get(f"{ns}/{short.upper()}")


R = make_engine_resolver(_lookup)


@pytest.mark.parametrize("q,echo", [
    ("get works where topic is in (col_abc123)",
     "get works where topic is in the set [Climate topics](col_abc123)"),
    ("get works where it cites works in (col_abc123)",
     "get works where it cites a work in the set [Climate topics](col_abc123)"),
    ("get works where topic is in (col_unknown)",
     "get works where topic is in the set (col_unknown)"),
    ("get each author in (col_auth9); then get all that author's works; then calculate count",
     "get each author in [Our lab](col_auth9); then, get all that author's works; "
     "finally, summarize using count"),
    ("get each institution in (I63966007, I97018004); then get all that institution's works",
     "get each institution in ([Massachusetts Institute of Technology](I63966007), "
     "[Stanford University](I97018004)); then, get all that institution's works"),
    ("get authors where co-author is (A5066175077 or A1)",
     "get authors where co-author is ([Jane Smith](A1) or [Stephen Hawking](A5066175077))"),
    ("get works where year > 2020; then group those works by author where that author is "
     "not in (col_auth9) and co-author is not (A1); then calculate count",
     "get works where year > 2020; then, group those works by author where co-author is "
     "not [Jane Smith](A1) and that author is not in the set [Our lab](col_auth9); "
     "finally, summarize using count"),
    ("get works where year >= 2016; then group those works into ((institution is "
     "(I99464096)), (country is (BE))); then calculate count",
     "get works where year >= 2016; then, group those works into (institution is "
     "[KU Leuven](I99464096), country is [Belgium](BE)); finally, summarize using count"),
])
def test_names_and_round_trip(q, echo):
    o = canonicalize_oqo(parse(q))
    assert render_pipeline_line(o, R) == echo
    assert canonicalize_oqo(parse(echo)).to_dict() == o.to_dict()


def test_named_set_conditions_may_open_with_a_parenthesis():
    q = ("get works where year >= 2016; then group those works into ((institution is "
         "I99464096 or country is BE) and year > 2020, year >= 2021); then calculate count")
    o = canonicalize_oqo(parse(q))
    assert len(o.group_by[0].conditions) == 2
    echo = render_pipeline_line(o, R)
    assert canonicalize_oqo(parse(echo)).to_dict() == o.to_dict()


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.mark.parametrize("status,body,want", [
    (200, {"id": "col_x", "display_name": "Our lab"}, "Our lab"),
    (404, {"error": "not found"}, None),
    (500, {}, None),
])
def test_collection_name_lookup(monkeypatch, status, body, want):
    from core import collection_resolver as C
    monkeypatch.setattr(C.settings, "USERS_API_URL", "https://users.example")
    monkeypatch.setattr(C.requests, "get", lambda *a, **k: _Resp(status, body))
    assert C.collection_display_name("col_x") == want


def test_collection_name_lookup_never_raises(monkeypatch):
    from core import collection_resolver as C

    def boom(*a, **k):
        raise C.requests.Timeout("slow")
    monkeypatch.setattr(C.settings, "USERS_API_URL", "https://users.example")
    monkeypatch.setattr(C.requests, "get", boom)
    assert C.collection_display_name("col_x") is None
