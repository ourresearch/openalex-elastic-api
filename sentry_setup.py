"""Sentry error reporting for openalex-elastic-api and openalex-search-api (oxjob #1685).

Both Heroku apps run this code; each has its own SENTRY_DSN (its own Sentry project).
Errors only: no tracing, no profiling, no Sentry Logs, no PII. A no-op when
SENTRY_DSN is unset.

What reaches Sentry: unhandled exceptions (Flask integration) and ERROR log records,
except two kinds of user mistakes that would otherwise flood it:
- APIError responses (bad filters, bad pagination: 4xx), which app.py's error handler
  logs at ERROR through app.logger, ~110 a minute. That logger is ignored.
- Elasticsearch rejecting a user's query text (unbalanced quotes, query_string syntax,
  too many clauses). app.py answers those with a JSON 400 (oxjob #1889), so they never
  arrive here as unhandled; the filter stays as a backstop. Any other BadRequestError
  (a query our code built wrongly, a missing mapping) is still reported.
"""
import os

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import ignore_logger

from core.user_query_errors import is_user_query_error

_initialized = False


def _before_send(event, hint):
    exc_info = hint.get("exc_info") if hint else None
    if not exc_info:
        return event
    exc = exc_info[1]
    if is_user_query_error(exc):
        return None
    # Sentry titles an elasticsearch ApiError by its .message, which is only the
    # error type ("search_phase_execution_exception") for every ES 400; use str(exc),
    # which carries the root cause's reason, so issues say what went wrong.
    if type(exc).__module__.startswith("elasticsearch") and hasattr(exc, "body"):
        for value in (event.get("exception") or {}).get("values") or []:
            if value.get("type") == type(exc).__name__:
                value["value"] = str(exc)[:1000]
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
