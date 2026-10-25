"""The side-door check (oxjob #1782): requests without the proxy's secret are logged, or refused in enforce mode.

Needs no app context: runs under --noconftest.
"""
import logging

import pytest
from flask import Flask

from core.origin_key import HEADER, MissLog, init_origin_key_check

SECRET = "s3cret-value"


def make_client(secret=SECRET, mode=None):
    app = Flask(__name__)
    app.config["ORIGIN_SHARED_SECRET"] = secret
    app.config["ORIGIN_KEY_MODE"] = mode
    init_origin_key_check(app)

    @app.route("/works")
    def works():
        return {"ok": True}

    return app.test_client()


def misses(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("origin_key_miss ")]


@pytest.mark.parametrize("secret,mode", [(None, None), (SECRET, "off")])
def test_check_off(caplog, secret, mode):
    client = make_client(secret=secret, mode=mode)
    with caplog.at_level(logging.WARNING):
        assert client.get("/works").status_code == 200
    assert misses(caplog) == []


def test_enforce_without_secret_says_so(caplog):
    with caplog.at_level(logging.ERROR):
        client = make_client(secret=None, mode="enforce")
    assert client.get("/works").status_code == 200
    assert any("origin check is OFF" in r.getMessage() for r in caplog.records)


def test_log_mode_serves_and_logs_missing_and_wrong(caplog):
    client = make_client()
    with caplog.at_level(logging.WARNING):
        assert client.get("/works").status_code == 200
        assert client.get("/works", headers={HEADER: "nope"}).status_code == 200
    lines = misses(caplog)
    assert len(lines) == 2
    assert "reason=missing" in lines[0]
    assert "reason=wrong" in lines[1]


def test_right_secret_is_silent(caplog):
    client = make_client(mode="enforce")
    with caplog.at_level(logging.WARNING):
        assert client.get("/works", headers={HEADER: SECRET}).status_code == 200
    assert misses(caplog) == []


def test_enforce_refuses_misses():
    client = make_client(mode="enforce")
    assert client.get("/works").status_code == 403
    assert client.get("/works", headers={HEADER: SECRET + "x"}).status_code == 403
    assert client.get("/works", headers={HEADER: ""}).status_code == 403


def test_enforce_lets_preflight_through():
    client = make_client(mode="enforce")
    assert client.options("/works").status_code == 200


def test_unknown_mode_counts_as_log():
    client = make_client(mode="enforec")
    assert client.get("/works").status_code == 200


def test_rotation_accepts_both_secrets():
    client = make_client(secret="new-one, old-one", mode="enforce")
    assert client.get("/works", headers={HEADER: "new-one"}).status_code == 200
    assert client.get("/works", headers={HEADER: "old-one"}).status_code == 200
    assert client.get("/works", headers={HEADER: "new-one, old-one"}).status_code == 403


def test_line_never_holds_the_secret_query_string_or_ip(caplog):
    client = make_client()
    with caplog.at_level(logging.WARNING):
        client.get(
            "/works?api_key=CUSTOMERKEY&mailto=a@b.org",
            headers={
                HEADER: "almost-" + SECRET,
                "X-Forwarded-For": "10.1.2.3, 203.0.113.9",
                "User-Agent": "python-requests/2.31",
                "CF-Worker": "example.org",
                "X-Request-Id": "abc reason=fake",
            },
        )
    (line,) = misses(caplog)
    assert SECRET not in line
    assert "CUSTOMERKEY" not in line and "a@b.org" not in line
    assert "203.0.113.9" not in line and "10.1.2.3" not in line
    assert 'path="/works"' in line
    assert 'ua="python-requests/2.31"' in line
    assert 'cf_worker="example.org"' in line
    assert 'req="abc reason=fake"' in line  # quoted: a client can't forge a field


def test_ip_hash_is_stable_per_last_hop(caplog):
    client = make_client()
    with caplog.at_level(logging.WARNING):
        client.get("/works", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"})
        client.get("/works", headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.9"})
        client.get("/works", headers={"X-Forwarded-For": "203.0.113.10"})
    hashes = [line.split("ip_hash=")[1].split()[0] for line in misses(caplog)]
    assert hashes[0] == hashes[1] != hashes[2]


def test_sampler_caps_lines_per_minute_and_reports_skips(caplog):
    now = [0.0]
    log = MissLog(limit=2, warn=logging.getLogger("test").warning, clock=lambda: now[0])
    with caplog.at_level(logging.WARNING):
        assert [log.should_log() for _ in range(5)] == [True, True, False, False, False]
        now[0] = 61.0
        assert log.should_log() is True
    assert "origin_key_miss_skipped count=3" in [r.getMessage() for r in caplog.records]
