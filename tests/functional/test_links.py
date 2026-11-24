"""/links (oxjob #1490): work-to-work links read from the `links` index, each {origin, target, link_type} as ids.
ES is faked; merged ids are off.

    PYTHONPATH=. venv/bin/python -m pytest tests/functional/test_links.py -q -p no:cacheprovider
"""
import pytest
from elasticsearch_dsl import AttrDict

import links.views as lv
from core.cursor import decode_cursor, encode_cursor

U = "https://openalex.org/"
R = U + "relationships/"
LT = U + "link-types/"
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
    """Serves `links` (docs) matching the query's filters in stored order (the list order stands in for _doc)."""
    links = []
    last = None
    closed = []

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
        b = self.body["query"]["bool"]
        want = {k: set(v) for clause in b.get("filter", []) + b.get("must", []) for k, v in clause["terms"].items()}
        rows = [d for d in FakeSearch.links if all(d[k] in v for k, v in want.items())]
        hits = [_Hit({**d, "meta": {"sort": [i]}}) for i, d in enumerate(rows)]
        if "search_after" in self.body:
            hits = [h for h in hits if h.meta.sort[0] > self.body["search_after"][0]]
        hits = hits[self.slice] if self.slice is not None else hits[:self.body.get("size", 10)]
        r = _Response(hits, len(rows))
        r._d_ = {"pit_id": self.body["pit"]["id"]} if "pit" in self.body else {}
        return r


@pytest.fixture(autouse=True)
def fake_es(monkeypatch):
    monkeypatch.setattr(lv, "Search", FakeSearch)
    monkeypatch.setattr(lv, "merged_winner", lambda short: None)
    monkeypatch.setattr(lv, "open_pit", lambda: "pit-1")
    monkeypatch.setattr(lv, "close_pit", lambda pit_id: FakeSearch.closed.append(pit_id))
    FakeSearch.closed = []
    FakeSearch.links = [doc("W1001", "W1009", "volume"), doc("W1001", "W1002", "citation"),
                        doc("W1001", "W1003", "citation"), doc("W1001", "W1004", "citation")]


def get(client, url):
    r = client.get(url)
    return r.status_code, r.get_json()


# --- requests that name no work, or ask for something /links doesn't do --------------------------

@pytest.mark.parametrize("url", ["/links", "/links?filter=link_type:citation", "/links?filter=origin:"])
def test_a_request_must_name_a_work(client, url):
    status, body = get(client, url)
    assert status == 400
    assert "/links?filter=origin:W2741809807" in body["message"]


@pytest.mark.parametrize("url", ["/links?filter=from:W1001", "/links?filter=to:W1001"])
def test_the_old_from_and_to_names_answer_400_naming_the_new_ones(client, url):
    status, body = get(client, url)
    assert status == 400 and "origin, target and link_type" in body["message"]


@pytest.mark.parametrize("url", [
    "/links?filter=cites:W1001", "/links?filter=origin:A123", "/links?filter=origin:W1001|W1002",
    "/links?filter=origin:!W1001", "/links?filter=origin:W1001,origin:W1002",
    "/links?filter=origin:W1001,link_type:cites", "/links?filter=origin:W1001&sort=id",
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

def test_query_reads_the_links_index_in_stored_order(client):
    get(client, "/links?filter=target:W1002")
    q = FakeSearch.last["query"]["bool"]
    assert FakeSearch.last["index"] == "links"
    assert q["filter"] == [{"terms": {"target": [U + "W1002"]}}]
    assert "must" not in q  # every relationship: no clause
    assert FakeSearch.last["sort"] == ("_doc",)


def test_a_named_relationship_is_a_must_not_a_filter(client):
    get(client, "/links?filter=target:W1002,link_type:component|part")
    q = FakeSearch.last["query"]["bool"]
    assert q["must"] == [{"terms": {"relationship": [R + "component", R + "part"]}}]
    assert q["filter"] == [{"terms": {"target": [U + "W1002"]}}]


def test_a_cursor_walk_reads_a_point_in_time_view_and_closes_it(client):
    _, body = get(client, "/links?filter=origin:W1001&per_page=3&cursor=*")
    assert FakeSearch.last["index"] is None and FakeSearch.last["pit"]["id"] == "pit-1"
    assert FakeSearch.last["sort"] == ("_shard_doc",)
    assert decode_cursor(body["meta"]["next_cursor"])[0] == "pit-1" and FakeSearch.closed == []
    _, body = get(client, f"/links?filter=origin:W1001&per_page=3&cursor={body['meta']['next_cursor']}")
    assert len(body["results"]) == 1 and body["meta"]["next_cursor"] is None and FakeSearch.closed == ["pit-1"]


def test_a_cursor_that_is_not_ours_answers_400(client):
    status, _ = get(client, f"/links?filter=origin:W1001&cursor={encode_cursor([5])}")
    assert status == 400


# --- results ----------------------------------------------------------------------------------------

def test_origin_lists_its_links(client):
    status, body = get(client, "/links?filter=origin:w1001")
    assert status == 200 and body["meta"]["count"] == 4
    assert body["results"][0] == {"origin": CITING, "target": BOOK, "link_type": LT + "volume"}
    assert [r["target"] for r in body["results"][1:]] == [U + "W1002", U + "W1003", U + "W1004"]  # stored order
    assert list(body["results"][0]) == ["origin", "target", "link_type"]  # no relationship (Casey, 24 Nov 2026)


def test_link_type_and_paging(client):
    _, body = get(client, "/links?filter=origin:https://openalex.org/W1001,link_type:citation&per_page=2&page=2")
    assert body["meta"]["count"] == 3
    assert [r["target"] for r in body["results"]] == [U + "W1004"]


def test_origin_and_target_give_the_links_between_two_works(client):
    _, body = get(client, "/links?filter=origin:W1001,target:W1009")
    assert [r["link_type"] for r in body["results"]] == [LT + "volume"]
    _, body = get(client, "/links?filter=origin:W1001,target:W1009,link_type:citation")
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
    assert seen == [U + f"W{100 + i}" for i in range(5)] + [U + "W999"] and pages == 3


def test_cursor_on_an_exactly_full_last_page_ends_there(client):
    _, body = get(client, "/links?filter=origin:W1001&per_page=2&cursor=*")
    _, body = get(client, f"/links?filter=origin:W1001&per_page=2&cursor={body['meta']['next_cursor']}")
    assert len(body["results"]) == 2 and body["meta"]["next_cursor"] is None


def test_page_mode_has_no_cursor(client):
    _, body = get(client, "/links?filter=origin:W1001&per_page=2")
    assert body["meta"]["page"] == 1 and body["meta"]["next_cursor"] is None and len(body["results"]) == 2


def test_cursor_round_trip():
    assert decode_cursor(encode_cursor(["pit-1", [241307]])) == ["pit-1", [241307]]


# --- link_type, the new name of relationship (oxjob #2481); /links dropped relationship 24 Nov 2026 -------

def test_every_link_carries_its_link_type_and_no_relationship(client):
    _, body = get(client, "/links?filter=origin:W1001")
    assert all("relationship" not in r for r in body["results"])
    assert [r["link_type"] for r in body["results"]] == [LT + "volume"] + [LT + "citation"] * 3


@pytest.mark.parametrize("value", ["citation", "Citation", "link-types/citation", "relationships/citation",
                                   "https://openalex.org/link-types/citation",
                                   "https://openalex.org/relationships/citation"])
def test_link_type_takes_every_id_form(client, value):
    _, body = get(client, f"/links?filter=origin:W1001,link_type:{value}")
    assert body["meta"]["count"] == 3
    assert FakeSearch.last["query"]["bool"]["must"] == [{"terms": {"relationship": [R + "citation"]}}]


def test_review_is_a_link_type(client):
    FakeSearch.links = [doc("W2001", "W1002", "review"), doc("W2002", "W1002", "citation")]
    _, body = get(client, "/links?filter=target:W1002,link_type:review")
    assert body["results"] == [{"origin": U + "W2001", "target": U + "W1002", "link_type": LT + "review"}]
    assert "review" in lv.RELATIONSHIPS and lv.relationships("review|volume") == ["volume", "review"]


@pytest.mark.parametrize("url", ["/links?filter=origin:W1001,relationship:citation",
                                 "/links?filter=origin:W1001,link_type:citation,relationship:citation"])
def test_the_old_relationship_filter_answers_400_naming_link_type(client, url):
    status, body = get(client, url)
    assert status == 400 and "use link_type:citation" in body["message"]


def test_a_bad_link_type_answers_400_under_its_own_name(client):
    status, body = get(client, "/links?filter=origin:W1001,link_type:cites")
    assert status == 400 and body["message"].startswith("link_type takes citation, ")


def test_the_examples_name_link_type():
    assert "link_type:citation" in lv.EXAMPLES and "review" in lv.EXAMPLES
