"""Request bodies gzipped at level 1, responses still asked for gzipped (oxjob #2016, core/es_node.py)."""
import gzip

from elastic_transport import NodeConfig, Urllib3HttpNode

from core.es_node import REQUEST_GZIP_LEVEL, FastGzipNode


def _node(monkeypatch, compress=True):
    sent = {}

    def perform(self, method, target, body=None, headers=None, **kw):
        sent.update(body=body, headers=dict(headers or {}), own=self._http_compress)
        return "ok"
    monkeypatch.setattr(Urllib3HttpNode, "perform_request", perform)
    return FastGzipNode(NodeConfig("https", "es.example", 443, http_compress=compress)), sent


def test_bodies_go_gzipped_at_level_1_and_responses_are_asked_gzipped(monkeypatch):
    node, sent = _node(monkeypatch)
    body = b'{"query": {"terms": {"id": ["W1", "W2"]}}}' * 1000
    assert node.perform_request("POST", "/works/_search", body=body, headers={"x": "1"}) == "ok"
    assert sent["headers"] == {"x": "1", "content-encoding": "gzip"}
    assert sent["body"] == gzip.compress(body, compresslevel=REQUEST_GZIP_LEVEL) and gzip.decompress(sent["body"]) == body
    assert sent["own"] is False                       # the base class doesn't gzip it a second time
    assert node.headers["accept-encoding"] == "gzip"  # responses: gzipped, as Elastic Cloud bills them


def test_without_http_compress_nothing_changes(monkeypatch):
    node, sent = _node(monkeypatch, compress=False)
    node.perform_request("POST", "/works/_search", body=b"{}")
    assert sent["body"] == b"{}" and "content-encoding" not in sent["headers"]
    assert "accept-encoding" not in node.headers
    node.perform_request("GET", "/", body=None)
    assert sent["body"] is None
