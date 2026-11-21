"""/links (oxjob #1490): work-to-work links read from the `links` index, each {origin, target, relationship} as ids.
ES is faked; merged ids are off.

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_links.py -q -p no:cacheprovider
"""
import pytest
from elasticsearch_dsl import AttrDict

import links.views as lv
from core.cursor import decode_cursor, encode_cursor

U = "https://openalex.org/"
R = U + "relationships/"
CITING = U + "W1001"
BOOK = U + "W1009"


def doc(origin, target, rel):
    return {"origin": U + origin, "target": U + target, "relationship": R + rel}


class _Hit(AttrDict):
    pass


class _Hits(list):
    def __init__(self, hits, total):
        super().__init__(hits)
        self.total = AttrDict({"value": total})


class _Response:
    def __init__(self, hits, total):
        self.hits = _Hits(hits, total)


class FakeSearch:
    """Serves `links` (docs) matching the query's filters, in the order the API asks for: parts first, then the other
    end's id."""
    links = []
    last = None

    def __init__(self, index=None):
        self.index = index
        self.body = {}
        self.slice = None

    def query(self, q):
        self.body["query"] = q.to_dict()
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
        FakeSearch.last = {**self.body, "index": self.index}
        f = self.body["query"]["bool"]["filter"]
        want = {k: set(v) for clause in f for k, v in clause["terms"].items()}
        rows = [d for d in FakeSearch.links if all(d[k] in v for k, v in want.items())]
        other = list(self.body["sort"][1])[0]
        parts = {R + p for p in lv.PART_OF}
        keyed = sorted(((0 if d["relationship"] in parts else 1, d[other], d["relationship"]), d) for d in rows)
        hits = [_Hit({**d, "meta": {"sort": [2.0 - key[0], key[1], key[2]]}}) for key, d in keyed]
        if "search_after" in self.body:
            a = self.body["search_after"]
            hits = [h for h in hits if (-h.meta.sort[0], h.meta.sort[1], h.meta.sort[2]) > (-a[0], a[1], a[2])]
        hits = hits[self.slice] if self.slice is not None else hits[:self.body.get("size", 10)]
        return _Response(hits, len(rows))


@pytest.fixture(autouse=True)
def fake_es(monkeypatch):
    monkeypatch.setattr(lv, "Search", FakeSearch)
    monkeypatch.setattr(lv, "merged_winner", lambda short: None)
    FakeSearch.links = [doc("W1001", "W1009", "volume"), doc("W1001", "W1002", "citation"),
                        doc("W1001", "W1003", "citation"), doc("W1001", "W1004", "citation")]


def get(client, url):
    r = client.get(url)
    return r.status_code, r.get_json()


# --- requests that name no work, or ask for something /links doesn't do --------------------------

@pytest.mark.parametrize("url", ["/links", "/links?filter=relationship:citation", "/links?filter=origin:"])
def test_a_request_must_name_a_work(client, url):
    status, body = get(client, url)
    assert status == 400
    assert "/links?filter=origin:W2741809807" in body["message"]


@pytest.mark.parametrize("url", ["/links?filter=from:W1001", "/links?filter=to:W1001"])
def test_the_old_from_and_to_names_answer_400_naming_the_new_ones(client, url):
    status, body = get(client, url)
    assert status == 400 and "origin, target and relationship" in body["message"]


@pytest.mark.parametrize("url", [
    "/links?filter=cites:W1001", "/links?filter=origin:A123", "/links?filter=origin:W1001|W1002",
    "/links?filter=origin:!W1001", "/links?filter=origin:W1001,origin:W1002",
    "/links?filter=origin:W1001,relationship:cites", "/links?filter=origin:W1001&sort=id",
    "/links?filter=target:W1001&group_by=relationship", "/links?filter=origin:W1001&per_page=500",
    "/links?filter=origin:W1001&page=2&cursor=*", "/links?filter=target:W1001&page=401&per_page=25",
])
def test_bad_requests_answer_400(client, url):
    status, _ = get(client, url)
    assert status == 400


def test_relationship_values_take_every_spelling():
    assert lv.relationships("Citation|relationships/volume") == ["citation", "volume"]
    assert lv.relationships("https://openalex.org/relationships/part") == ["part"]
    assert lv.relationships(None) == lv.RELATIONSHIPS


# --- the query -------------------------------------------------------------------------------------

def test_query_reads_the_links_index_and_ranks_parts_first(client):
    get(client, "/links?filter=target:W1002")
    q = FakeSearch.last["query"]["bool"]
    assert FakeSearch.last["index"] == "links"
    assert {"terms": {"target": [U + "W1002"]}} in q["filter"]
    assert {"terms": {"relationship": [R + r for r in lv.RELATIONSHIPS]}} in q["filter"]
    assert q["should"] == [{"constant_score": {"filter": {"terms": {"relationship": [R + r for r in lv.PART_OF]}},
                                               "boost": 1}}]
    assert FakeSearch.last["sort"] == ({"_score": {"order": "desc"}}, {"origin": {"order": "asc"}},
                                       {"relationship": {"order": "asc"}})


def test_origin_sorts_by_target(client):
    get(client, "/links?filter=origin:W1001")
    assert FakeSearch.last["sort"][1] == {"target": {"order": "asc"}}


# --- results ----------------------------------------------------------------------------------------

def test_origin_lists_parts_first_then_the_rest(client):
    status, body = get(client, "/links?filter=origin:w1001")
    assert status == 200 and body["meta"]["count"] == 4
    assert body["results"][0] == {"origin": CITING, "target": BOOK, "relationship": R + "volume"}
    assert [r["target"] for r in body["results"][1:]] == [U + "W1002", U + "W1003", U + "W1004"]
    assert list(body["results"][0]) == ["origin", "target", "relationship"]


def test_relationship_and_paging(client):
    _, body = get(client, "/links?filter=origin:https://openalex.org/W1001,relationship:citation&per_page=2&page=2")
    assert body["meta"]["count"] == 3
    assert [r["target"] for r in body["results"]] == [U + "W1004"]


def test_origin_and_target_give_the_links_between_two_works(client):
    _, body = get(client, "/links?filter=origin:W1001,target:W1009")
    assert [r["relationship"] for r in body["results"]] == [R + "volume"]
    _, body = get(client, "/links?filter=origin:W1001,target:W1009,relationship:citation")
    assert body["meta"]["count"] == 0 and body["results"] == []


def test_cursor_walks_every_link_and_ends(client):
    FakeSearch.links = [doc(f"W{100 + i}", "W1002", "citation") for i in range(5)] + [doc("W999", "W1002", "component")]
    seen, cursor, pages = [], "*", 0
    while cursor:
        _, body = get(client, f"/links?filter=target:W1002&per_page=2&cursor={cursor}")
        assert body["meta"]["count"] == 6 and body["meta"]["page"] is None
        seen += [r["origin"] for r in body["results"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
    assert seen == [U + "W999"] + [U + f"W{100 + i}" for i in range(5)] and pages == 3


def test_cursor_on_an_exactly_full_last_page_ends_there(client):
    _, body = get(client, "/links?filter=origin:W1001&per_page=2&cursor=*")
    _, body = get(client, f"/links?filter=origin:W1001&per_page=2&cursor={body['meta']['next_cursor']}")
    assert len(body["results"]) == 2 and body["meta"]["next_cursor"] is None


def test_page_mode_has_no_cursor(client):
    _, body = get(client, "/links?filter=origin:W1001&per_page=2")
    assert body["meta"]["page"] == 1 and body["meta"]["next_cursor"] is None and len(body["results"]) == 2


def test_cursor_round_trip():
    assert decode_cursor(encode_cursor([2.0, U + "W1", R + "citation"])) == [2.0, U + "W1", R + "citation"]
