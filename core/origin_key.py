"""Requests should reach this app only through the api.openalex.org proxy (oxjob #1782).

openalex-elastic-api and openalex-search-api also answer on their own herokuapp.com
hostnames (and elastic.api.openalex.org), which skips the proxy's keys, budgets,
enforcement list and Cloudflare's firewall. The proxy sends a shared secret in
X-OpenAlex-Origin-Key; this check notes, and later refuses, every request without it.

Config vars (set on BOTH Heroku apps; each `config:set` restarts that app):
  ORIGIN_SHARED_SECRET  the accepted secret, or several comma-separated so a rotation can
                        overlap (set "new,old" here, switch the proxy to new, then drop old).
                        Unset: the check is off.
  ORIGIN_KEY_MODE       "log" (default): log each miss and serve it anyway.
                        "enforce": answer a miss with 403.
                        "off": skip the check. Any other value counts as "log", so a typo
                        never blocks traffic.

Each process logs up to LOG_PER_MINUTE misses a minute, then one line saying how many it
skipped (fleet ceiling ~135 dynos x workers x 5 lines a minute, about 1 GB a day under a
flood). Lines start with "origin_key_miss" (not access-log shaped, so Better Stack's ingest
drop rules keep them). Better Stack redacts IPs at ingest, so a line carries a keyed hash of
the client IP instead: enough to count distinct callers. No health-check route exists
(2026-10-24); only OPTIONS preflights are exempt, since they return no data.
"""
import hashlib
import hmac
import json
import logging
import threading
import time

from flask import jsonify, request

HEADER = "X-OpenAlex-Origin-Key"
LOG_PER_MINUTE = 5


class MissLog:
    """Per-process sampler: up to `limit` lines a minute, then a count of the rest.

    shortcut: a minute's skip count is written when the next miss arrives in a later
    minute, so the last minute of a burst is never reported. Fine for spotting callers.
    """

    def __init__(self, limit, warn, clock=time.monotonic):
        self.limit = limit
        self.warn = warn
        self.clock = clock
        self.lock = threading.Lock()
        self.minute = None
        self.count = 0

    def should_log(self):
        minute = int(self.clock() // 60)
        with self.lock:
            if minute != self.minute:
                if self.count > self.limit:
                    self.warn("origin_key_miss_skipped count=%d", self.count - self.limit)
                self.minute, self.count = minute, 0
            self.count += 1
            return self.count <= self.limit


def _q(value, n=200):
    """A header value as a quoted, length-capped field, so it can't forge other fields."""
    return json.dumps((value or "")[:n])


def _client_ip():
    # Heroku's router appends the address that connected to it as the last X-Forwarded-For entry.
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[-1].strip() or (request.remote_addr or "")


def _miss_line(reason, hash_key):
    ip = _client_ip()
    ip_hash = hmac.new(hash_key, ip.encode(), hashlib.sha256).hexdigest()[:10] if ip else "-"
    return "origin_key_miss reason=%s host=%s method=%s path=%s ua=%s cf_worker=%s ip_hash=%s req=%s" % (
        reason,
        _q(request.host, 100),
        request.method,
        _q(request.path),  # path only: the query string can hold api_key / mailto
        _q(request.headers.get("User-Agent")),
        _q(request.headers.get("CF-Worker"), 100),  # zone of a Cloudflare Worker calling us
        ip_hash,
        _q(request.headers.get("X-Request-Id"), 64),
    )


def init_origin_key_check(app):
    keys = [s.strip().encode() for s in (app.config.get("ORIGIN_SHARED_SECRET") or "").split(",") if s.strip()]
    mode = (app.config.get("ORIGIN_KEY_MODE") or "log").strip().lower()
    if not keys:
        if mode == "enforce":
            # A lost secret must not silently reopen the side door. (Module logger: app.logger is
            # ignored by Sentry, this one reaches it.)
            logging.getLogger(__name__).error(
                "ORIGIN_KEY_MODE=enforce but ORIGIN_SHARED_SECRET is unset: origin check is OFF (oxjob #1782)"
            )
        return
    if mode == "off":
        return
    enforce = mode == "enforce"
    # app.logger, not a module logger: Flask's handler is what writes this app's lines to stderr (Heroku logs).
    misses = MissLog(LOG_PER_MINUTE, app.logger.warning)

    @app.before_request
    def check_origin_key():
        if request.method == "OPTIONS":
            return None
        got = request.headers.get(HEADER, "").encode()
        if got and any(hmac.compare_digest(got, k) for k in keys):
            return None
        if misses.should_log():
            misses.warn(_miss_line("wrong" if got else "missing", keys[0]))
        if enforce:
            # Not an APIError: its handler logs every error unsampled, which a flood would turn into a log bill.
            return jsonify({"error": "Forbidden", "message": "Please use https://api.openalex.org"}), 403
        return None
