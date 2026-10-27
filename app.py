import json
import time

import sentry_sdk
from elasticsearch.exceptions import BadRequestError as ESBadRequestError
from elasticsearch.exceptions import ConnectionTimeout as ESConnectionTimeout
from elasticsearch_dsl import connections
from flask import Flask, jsonify, request

import awards
import authors
import autocomplete
import concepts
import continents
import countries
import counts
import domains
import fields
import funder_search
import funders
import ids
import indexes
import institution_types
import institutions
import keywords
import languages
import licenses
import locations
import meta
import oa_statuses
import publishers
import query_translation
import query_translation.editor_views  # #357 OQL editor support (separate blueprint)
import query_translation.spec_views  # #361 OQL/OQO spec-artifact serving (separate blueprint)
import raw_affiliation_strings
import settings
import sdgs
import snapshots
import sources
import source_lists
import source_types
import study_designs
import subfields
import suggest
import topics
import works
import work_types
from core.collection_resolver import CollectionUrlIdsInQuery
from core.exceptions import APIError, APIQueryParamsError, QueryTimeoutError
from core.origin_key import init_origin_key_check
from core.user_query_errors import user_query_error_message
from extensions import cache
from sentry_setup import init_sentry


def create_app(config_object="settings"):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # oxjob #1782: note (later refuse) requests that skip the api.openalex.org proxy.
    init_origin_key_check(app)
    register_blueprints(app)
    register_extensions(app)
    register_errorhandlers(app)
    app.wsgi_app = CollectionUrlIdsInQuery(app.wsgi_app)

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response

    @app.after_request
    def inject_cost_usd(response):
        # A query priced from its plan (oxjob #1530) carries its own cost; the
        # proxy's up-front charge (X-Cost-USD) doesn't apply to it.
        if response.headers.get("X-Credits-Cost") is not None:
            return response
        cost_header = response.headers.get("X-Cost-USD") or request.headers.get("X-Cost-USD")
        if (
            cost_header is not None
            and response.content_type
            and "application/json" in response.content_type
        ):
            try:
                data = response.get_json(silent=True)
                if data and isinstance(data, dict) and "meta" in data:
                    data["meta"]["cost_usd"] = float(cost_header)
                    response.data = json.dumps(data, sort_keys=False)
            except (ValueError, TypeError):
                pass
        return response

    return app


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(awards.views.blueprint)
    app.register_blueprint(authors.views.blueprint)
    app.register_blueprint(autocomplete.views.blueprint)
    app.register_blueprint(concepts.views.blueprint)
    app.register_blueprint(continents.views.blueprint)
    app.register_blueprint(countries.views.blueprint)
    app.register_blueprint(counts.views.blueprint)
    app.register_blueprint(domains.views.blueprint)
    app.register_blueprint(fields.views.blueprint)
    app.register_blueprint(funder_search.views.blueprint)
    app.register_blueprint(funders.views.blueprint)
    app.register_blueprint(ids.views.blueprint)
    app.register_blueprint(indexes.views.blueprint)
    app.register_blueprint(institution_types.views.blueprint)
    app.register_blueprint(institutions.views.blueprint)
    app.register_blueprint(keywords.views.blueprint)
    app.register_blueprint(languages.views.blueprint)
    app.register_blueprint(licenses.views.blueprint)
    app.register_blueprint(locations.views.blueprint)
    app.register_blueprint(meta.views.blueprint)
    app.register_blueprint(oa_statuses.views.blueprint)
    app.register_blueprint(publishers.views.blueprint)
    app.register_blueprint(query_translation.views.blueprint)
    app.register_blueprint(query_translation.editor_views.blueprint)  # #357 OQL editor support
    app.register_blueprint(query_translation.spec_views.blueprint)  # #361 OQL/OQO spec artifacts
    app.register_blueprint(raw_affiliation_strings.views.blueprint)
    app.register_blueprint(sdgs.views.blueprint)
    app.register_blueprint(snapshots.views.blueprint)
    app.register_blueprint(sources.views.blueprint)
    app.register_blueprint(source_lists.views.blueprint)
    app.register_blueprint(source_types.views.blueprint)
    app.register_blueprint(study_designs.views.blueprint)
    app.register_blueprint(subfields.views.blueprint)
    app.register_blueprint(suggest.views.blueprint)
    app.register_blueprint(topics.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(work_types.views.blueprint)
    return None


def register_extensions(app):
    init_sentry()  # oxjob #1685: per-app DSN, environment/release/server_name, user errors filtered
    # oxjob #521: ES client timeout 15s -> 7s. The query timeout is a soft 5s
    # (returns partial), so a 15s client wait just pins a Heroku worker on doomed
    # queries long after the proxy (9s) gave up, exhausting workers -> H12s. 7s lets
    # the worker return cleanly just after the 5s query budget.
    # oxjob #1433: vector 15s -> 7s, for the same reason. The proxy gives up at 9s, so a slower semantic search can
    # never reach its caller, and while the vector cluster was overloaded (13 and 15 Oct) every search ran on to the
    # 12s gunicorn kill, keeping the cluster busy with searches nobody was waiting for. Closing the connection at 7s
    # lets Elasticsearch cancel the search; vector_index.py turns the timeout into a 503 the proxy's ladder counts.
    # oxjob #1682: http_compress asks ES for gzip. Elastic Cloud bills every response byte
    # as data out (~16 TB/day, 99% of it search responses to this app); gzip cuts it ~6x.
    # Measured from a dyno: 25-result pages unchanged, 100-200-result pages +~20 ms.
    connections.create_connection('default', hosts=[settings.ES_URL_WALDEN], timeout=7, http_compress=True)
    connections.create_connection('walden', hosts=[settings.ES_URL_WALDEN], timeout=7, http_compress=True)
    if settings.ES_VECTOR_SEARCH_URL:
        connections.create_connection('vector', hosts=[settings.ES_VECTOR_SEARCH_URL], timeout=7, http_compress=True)
    cache.init_app(app)


def register_errorhandlers(app):
    """Register error handlers."""

    def handle_exception(err):
        """Return custom JSON when APIError or its children are raised"""
        response = {"error": err.description, "message": ""}
        if len(err.args) > 0:
            response["message"] = err.args[0]
        # Machine-readable code where an error defines one (e.g. a collection the
        # caller can't read, oxjob #646). Additive: older errors carry none.
        if getattr(err, "error_code", None):
            response["code"] = err.error_code
        # Add some logging so that we can monitor different types of errors
        app.logger.error("{}: {}".format(err.description, response["message"]))
        headers = {}
        # 503s get a Retry-After hint so polite clients back off rather than
        # hammering during a users-api blip (security review M5).
        if err.code == 503:
            headers["Retry-After"] = "30"
        return jsonify(response), err.code, headers

    app.errorhandler(APIError)(handle_exception)

    def handle_es_timeout(err):
        """Elasticsearch didn't answer within the client timeout (7 s). Still sent to
        Sentry, where these timeouts are a health signal (a handled error isn't)."""
        sentry_sdk.capture_exception(err)  # a no-op when Sentry isn't set up
        return handle_exception(QueryTimeoutError(
            "This query took too long and was stopped before it finished. Narrow it "
            "(a shorter year range, a smaller institution or topic, fewer group_by "
            "fields) and try again."
        ))

    app.errorhandler(ESConnectionTimeout)(handle_es_timeout)

    def handle_es_bad_request(err):
        """Elasticsearch rejected the request. When it rejected the user's own search
        text, answer a JSON 400 that says what to fix (core/user_query_errors.py).
        Anything else is our bug: re-raised, so it stays a 500 and reaches Sentry."""
        message = user_query_error_message(err)
        if message is None:
            raise err
        app.logger.warning("search text rejected by Elasticsearch: %s", str(err)[:500])
        return handle_exception(APIQueryParamsError(message))

    app.errorhandler(ESBadRequestError)(handle_es_bad_request)


if __name__ == '__main__':
    app = create_app()
    app.run()