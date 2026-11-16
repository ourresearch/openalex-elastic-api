"""/links (oxjob #1490): work-to-work links read from the works index. ES is faked; merged ids are off.

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_links.py -q -p no:cacheprovider
"""
import pytest
from elasticsearch_dsl import AttrDict

import links.views as lv
from core.cursor import decode_cursor, encode_cursor

U = "https://openalex.org/"
CITING = U + "W1001"
BOOK = U + "W1009"

DOCS = {
    CITING: {"id": CITING, "display_name": "A chapter", "publication_date": "2020-01-01",
             "parent_works": [{"id": BOOK, "display_name": "The book", "relationship": "volume"}],
             "referenced_works": [U + "W1002", U + "W1003", U + "W1004"]},
    U + "W1002": {"id": U + "W1002", "display_name": "Two"},
    U + "W1003": {"id": U + "W1003", "display_name": "Three"},
    BOOK: {"id": BOOK, "display_name": "The book"},
}


class _Hit(AttrDict):
    def to_dict(self):
        return {k: v for k, v in self._d_.items() if k != "meta"}


class _Response:
    def __init__(self, hits, total):
        self.hits = _Hits(hits, total)


class _Hits(list):
    def __init__(self, hits, total):
        super().__init__(hits)
        self.total = AttrDict({"value": total})


class FakeSearch:
    """Answers ids queries from DOCS and the incoming-links query from INCOMING."""
    incoming = []   # (source, matched_queries, sort)
    last = None     # the last incoming-links query

    def __init__(self, index=None):
        self.body = {}
        self.slice = None

    def query(self, q):
        self.body["query"] = q.to_dict()
        return self

    def source(self, fields):
        return self

    def sort(self, *keys):
        self.body["sort"] = keys
        return self

    def extra(self, **kw):
        self.body.update(kw)
        return self

    def __getitem__(self, s):
        self.slice = s
        return self

    def execute(self):
        q = self.body["query"]
        if "ids" in q:
            hits = [_Hit({**DOCS[i], "meta": {}}) for i in q["ids"]["values"] if i in DOCS]
            return _Response(hits, len(hits))
        FakeSearch.last = self.body
        rows = FakeSearch.incoming
        if "search_after" in self.body:
            rows = [r for r in rows if r[2] < self.body["search_after"]]
        hits = [_Hit({**src, "meta": {"matched_queries": mq, "sort": sort}}) for src, mq, sort in rows]
        total = len(FakeSearch.incoming)
        if self.slice is not None:
            hits = hits[self.slice]
        else:
            hits = hits[:self.body.get("size", 10)]
        return _Response(hits, total)


@pytest.fixture(autouse=True)
def fake_es(monkeypatch):
    monkeypatch.setattr(lv, "Search", FakeSearch)
    monkeypatch.setattr(lv, "merged_winner", lambda short: None)
    FakeSearch.incoming = []


def get(client, url):
    r = client.get(url)
    return r.status_code, r.get_json()


# --- requests that name no work, or ask for something /links doesn't do --------------------------

@pytest.mark.parametrize("url", ["/links", "/links?filter=relationship:citation", "/links?filter=from:"])
def test_a_request_must_name_a_work(client, url):
    status, body = get(client, url)
    assert status == 400
    assert "/links?filter=from:W2741809807" in body["message"]


@pytest.mark.parametrize("url", [
    "/links?filter=cites:W1001", "/links?filter=from:A123", "/links?filter=from:W1001|W1002", "/links?filter=from:!W1001",
    "/links?filter=from:W1001,from:W1002", "/links?filter=from:W1001,relationship:cites", "/links?filter=from:W1001&sort=id",
    "/links?filter=to:W1001&group_by=relationship", "/links?filter=from:W1001&per_page=500",
    "/links?filter=from:W1001&page=2&cursor=*", "/links?filter=to:W1001&page=401&per_page=25",
])
def test_bad_requests_answer_400(client, url):
    status, _ = get(client, url)
    assert status == 400


def test_relationship_values_take_every_spelling():
    assert lv.relationships("Citation|relationships/volume") == ["citation", "volume"]
    assert lv.relationships("https://openalex.org/relationships/part") == ["part"]
    assert lv.relationships(None) == lv.RELATIONSHIPS
    assert lv.RELATIONSHIPS[0] == "citation" and "citation" not in lv.PART_OF


# --- from: a work's links out -------------------------------------------------------------------

def test_from_lists_parents_then_references_in_order(client):
    status, body = get(client, "/links?filter=from:w1001")
    assert status == 200
    assert body["meta"]["count"] == 4
    assert body["results"][0] == {"from": {"id": CITING, "display_name": "A chapter"},
                                  "to": {"id": BOOK, "display_name": "The book"}, "relationship": "volume"}
    assert [(r["to"]["id"], r["to"]["display_name"], r["relationship"]) for r in body["results"][1:]] == [
        (U + "W1002", "Two", "citation"), (U + "W1003", "Three", "citation"),
        (U + "W1004", None, "citation")]  # a cited id with no works doc keeps its id, no name
    assert list(body["results"][0]) == ["from", "to", "relationship"]


def test_from_with_relationship_and_paging(client):
    _, body = get(client, "/links?filter=from:https://openalex.org/W1001,relationship:citation&per_page=2&page=2")
    assert body["meta"]["count"] == 3
    assert [r["to"]["id"] for r in body["results"]] == [U + "W1004"]


def test_from_cursor_walks_every_link(client):
    seen, cursor = [], "*"
    while cursor:
        _, body = get(client, f"/links?filter=from:W1001&per_page=3&cursor={cursor}")
        seen += [r["to"]["id"] for r in body["results"]]
        cursor = body["meta"]["next_cursor"]
    assert seen == [BOOK, U + "W1002", U + "W1003", U + "W1004"]


def test_from_and_to_gives_the_links_between_two_works(client):
    _, body = get(client, "/links?filter=from:W1001,to:W1009")
    assert [r["relationship"] for r in body["results"]] == ["volume"]
    _, body = get(client, "/links?filter=from:W1001,to:W1009,relationship:citation")
    assert body["meta"]["count"] == 0 and body["results"] == []


def test_from_an_unknown_work_has_no_links(client):
    status, body = get(client, "/links?filter=from:W777")
    assert status == 200 and body["meta"]["count"] == 0


# --- to: links into a work ------------------------------------------------------------------------

def _incoming(n):
    return [({"id": U + f"W{100 + i}", "display_name": f"Citing {i}", "parent_works": None}, ["citation"],
             [2_000_000 - i, U + f"W{100 + i}"]) for i in range(n)]


def test_to_query_names_the_citation_clause_and_sorts_newest_first(client):
    get(client, "/links?filter=to:W1002")
    q = FakeSearch.last["query"]["bool"]
    assert q["minimum_should_match"] == 1
    assert {"terms": {"referenced_works": [U + "W1002"], "_name": "citation"}} in q["should"]
    assert {"terms": {"parent_works.id": [U + "W1002"]}} in q["should"]
    assert FakeSearch.last["sort"][0] == {"publication_date": {"order": "desc", "missing": "_last"}}


def test_to_one_part_of_kind_narrows_the_parent_clause(client):
    get(client, "/links?filter=to:W1009,relationship:volume")
    (clause,) = FakeSearch.last["query"]["bool"]["should"]
    assert clause == {"bool": {"must": [{"terms": {"parent_works.id": [BOOK]}},
                                        {"terms": {"parent_works.relationship": ["volume"]}}]}}


def test_to_builds_links_from_each_hit(client):
    chapter = {"from": {"id": CITING, "display_name": "A chapter"}, "to": {"id": BOOK, "display_name": "The book"}}
    FakeSearch.incoming = [(DOCS[CITING], None, [1, CITING])]
    _, body = get(client, "/links?filter=to:W1009")
    assert body["results"] == [{**chapter, "relationship": "volume"}]
    # a chapter that also cites its book: two links, part-of first
    FakeSearch.incoming = [(DOCS[CITING], ["citation"], [1, CITING])]
    _, body = get(client, "/links?filter=to:W1009")
    assert body["results"] == [{**chapter, "relationship": "volume"}, {**chapter, "relationship": "citation"}]


def test_to_cursor_walks_every_link_and_ends(client):
    FakeSearch.incoming = _incoming(5)
    seen, cursor, pages = [], "*", 0
    while cursor:
        _, body = get(client, f"/links?filter=to:W1002&per_page=2&cursor={cursor}")
        assert body["meta"]["count"] == 5 and body["meta"]["page"] is None
        seen += [r["from"]["id"] for r in body["results"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
    assert seen == [U + f"W{100 + i}" for i in range(5)] and pages == 3


def test_to_cursor_on_an_exactly_full_last_page_ends_there(client):
    FakeSearch.incoming = _incoming(4)
    _, body = get(client, "/links?filter=to:W1002&per_page=2&cursor=*")
    _, body = get(client, f"/links?filter=to:W1002&per_page=2&cursor={body['meta']['next_cursor']}")
    assert len(body["results"]) == 2 and body["meta"]["next_cursor"] is None


def test_page_mode_has_no_cursor(client):
    FakeSearch.incoming = _incoming(3)
    _, body = get(client, "/links?filter=to:W1002&per_page=2")
    assert body["meta"]["page"] == 1 and body["meta"]["next_cursor"] is None and len(body["results"]) == 2


def test_cursor_round_trip():
    assert decode_cursor(encode_cursor([25])) == [25]
