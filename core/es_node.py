"""The Elasticsearch client's HTTP node, with request bodies gzipped at level 1 (oxjob #2016).

`http_compress=True` (oxjob #1682) asks ES for gzipped responses, which Elastic Cloud bills as data out, and also
gzips every request body at gzip's default level 9. A set in parentheses sends its ids in the body: 659K work ids
took about 0.8 s of CPU per request at level 9 and about 0.05 s at level 1, and a sampled "cites" query paid ~1 s of
it (#1930). Requests are data in, which isn't billed, so this node keeps asking for gzipped responses and compresses
what it sends at level 1.
"""
import gzip

from elastic_transport import Urllib3HttpNode

REQUEST_GZIP_LEVEL = 1


class FastGzipNode(Urllib3HttpNode):
    def __init__(self, config):
        super().__init__(config)
        # keeps the accept-encoding: gzip header set above; bodies are compressed below instead of by the base class
        self._gzip_bodies = self._http_compress
        self._http_compress = False

    def perform_request(self, method, target, body=None, headers=None, **kw):
        if body and self._gzip_bodies:
            body = gzip.compress(body, compresslevel=REQUEST_GZIP_LEVEL)
            headers = dict(headers or {}, **{"content-encoding": "gzip"})
        return super().perform_request(method, target, body=body, headers=headers, **kw)
