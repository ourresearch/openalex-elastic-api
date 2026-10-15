"""Sentry error reporting for openalex-elastic-api and openalex-search-api (oxjob #1685).

Both Heroku apps run this code; each has its own SENTRY_DSN (its own Sentry project).
Errors only: no tracing, no profiling, no Sentry Logs, no PII. A no-op when
SENTRY_DSN is unset.

What reaches Sentry: unhandled exceptions (Flask integration) and ERROR log records,
except two kinds of user mistakes that would otherwise flood it:
- APIError responses (bad filters, bad pagination: 4xx), which app.py's error handler
  logs at ERROR through app.logger, ~110 a minute. That logger is ignored.
- Elasticsearch rejecting a user's query text (unbalanced quotes, query_string syntax,
  too many clauses). The API still answers those with a 500 today; they are dropped
  here so a real 500 stays visible. Any other BadRequestError (a query our code built
  wrongly, a missing mapping) is still reported.
"""
import os

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import ignore_logger

_initialized = False

# Text Elasticsearch puts in a 400 when the *user's* query can't be parsed or is too big.
_USER_QUERY_MARKERS = (
    "token_mgr_error",
    "Failed to parse query",
    "Cannot parse",
    "parse_exception",
    "too_many_clauses",
    "too_many_nested_clauses",
    "maxClauseCount",
)


def _is_user_query_error(exc):
    try:
        from elasticsearch import BadRequestError
    except ImportError:  # pragma: no cover
        return False
    if not isinstance(exc, BadRequestError):
        return False
    text = f"{exc} {getattr(exc, 'body', '')}"
    return any(marker in text for marker in _USER_QUERY_MARKERS)


def _before_send(event, hint):
    exc_info = hint.get("exc_info") if hint else None
    if exc_info and _is_user_query_error(exc_info[1]):
        return None
    return event


def init_sentry():
    global _initialized
    dsn = os.environ.get("SENTRY_DSN")
    if _initialized or not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        # HEROKU_* come from Heroku's runtime-dyno-metadata lab feature.
        release=os.environ.get("HEROKU_SLUG_COMMIT") or os.environ.get("HEROKU_RELEASE_VERSION"),
        server_name=os.environ.get("DYNO"),
        send_default_pii=False,
        traces_sample_rate=0,
        # No sentry-trace/baggage headers on outbound calls (ES, users-api, Databricks): no tracing here.
        trace_propagation_targets=[],
        before_send=_before_send,
        # Flask only, as before (sentry-sdk 1.10 was given FlaskIntegration). The
        # auto-enabled set crashes at boot against our pins: 2.71's Redis integration
        # raises AttributeError on redis 4.3.1 (redis.asyncio.cluster.ClusterPipeline),
        # which took every dyno of both apps down on 2026-10-14. The Anthropic/OpenAI
        # ones would also report caught model-call failures as unhandled.
        auto_enabling_integrations=False,
        integrations=[FlaskIntegration()],
    )
    # app.py's APIError handler logs every 4xx at ERROR through Flask's app.logger.
    ignore_logger("app")
    # gunicorn --preload inits Sentry in the arbiter too, which logs routine worker
    # recycling and every deploy's "Worker was sent SIGTERM!" at ERROR.
    ignore_logger("gunicorn.error")
    ignore_logger("gunicorn.access")
    _initialized = True
