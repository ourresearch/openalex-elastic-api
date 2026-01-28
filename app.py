import os
import time

import sentry_sdk
from elasticsearch_dsl import connections
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager
from sentry_sdk.integrations.flask import FlaskIntegration

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
import institution_types
import institutions
import keywords
import languages
import licenses
import locations
import oa_statuses
import oql
import publishers
import query_translation
import raw_affiliation_strings
import settings
import sdgs
import sources
import source_types
import subfields
import suggest
import topics
import vector_search
import works
import work_types
from core.exceptions import APIError
from extensions import cache, db


def create_app(config_object="settings"):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # JWT used by Analytics endpoints
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = False
    app.config['JWT_VERIFY_SUB'] = False
    app.config['JWT_TOKEN_LOCATION'] = ('headers', 'query_string')
    jwt = JWTManager(app)

    register_blueprints(app)
    register_extensions(app)
    register_errorhandlers(app)

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response

    # Test endpoint for timeout behavior verification (job #29)
    # Usage: GET /_test/sleep?seconds=60
    # This helps verify whether Gunicorn kills workers after --timeout seconds
    @app.route('/_test/sleep')
    def test_sleep():
        sleep_seconds = request.args.get('seconds', default=60, type=int)
        # Cap at 5 minutes to prevent abuse
        sleep_seconds = min(sleep_seconds, 300)

        start_time = time.time()
        app.logger.warning(f"[TIMEOUT TEST] Starting sleep for {sleep_seconds}s")

        time.sleep(sleep_seconds)

        elapsed = time.time() - start_time
        app.logger.warning(f"[TIMEOUT TEST] Completed after {elapsed:.2f}s")

        return jsonify({
            "test": "timeout_verification",
            "requested_sleep_seconds": sleep_seconds,
            "actual_elapsed_seconds": round(elapsed, 2),
            "message": "If you see this, the request completed successfully without being killed by Gunicorn timeout"
        })

    # Test endpoint that simulates external HTTP call (like ES query)
    # Usage: GET /_test/http_wait?seconds=60
    # Note: httpbin.org caps at 10s, so we loop to reach requested duration
    @app.route('/_test/http_wait')
    def test_http_wait():
        import requests as http_requests
        wait_seconds = request.args.get('seconds', default=60, type=int)
        wait_seconds = min(wait_seconds, 300)

        start_time = time.time()
        app.logger.warning(f"[TIMEOUT TEST] Starting HTTP wait for {wait_seconds}s (looped)")

        # httpbin.org caps at 10s, so loop multiple calls to reach target duration
        calls_made = 0
        statuses = []
        try:
            while time.time() - start_time < wait_seconds:
                remaining = wait_seconds - (time.time() - start_time)
                delay = min(10, max(1, int(remaining)))  # httpbin caps at 10s
                resp = http_requests.get(f"https://httpbin.org/delay/{delay}", timeout=delay + 10)
                statuses.append(resp.status_code)
                calls_made += 1
                app.logger.warning(f"[TIMEOUT TEST] Call {calls_made} completed, elapsed: {time.time() - start_time:.2f}s")
        except Exception as e:
            statuses.append(f"error: {e}")

        elapsed = time.time() - start_time
        app.logger.warning(f"[TIMEOUT TEST] HTTP wait completed after {elapsed:.2f}s ({calls_made} calls)")

        return jsonify({
            "test": "http_wait_verification",
            "requested_wait_seconds": wait_seconds,
            "actual_elapsed_seconds": round(elapsed, 2),
            "httpbin_calls_made": calls_made,
            "httpbin_statuses": statuses,
            "message": "If you see this, the HTTP request completed without being killed by Gunicorn timeout"
        })

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
    app.register_blueprint(institution_types.views.blueprint)
    app.register_blueprint(institutions.views.blueprint)
    app.register_blueprint(keywords.views.blueprint)
    app.register_blueprint(languages.views.blueprint)
    app.register_blueprint(licenses.views.blueprint)
    app.register_blueprint(locations.views.blueprint)
    app.register_blueprint(oa_statuses.views.blueprint)
    app.register_blueprint(oql.views.blueprint)
    app.register_blueprint(publishers.views.blueprint)
    app.register_blueprint(query_translation.views.blueprint)
    app.register_blueprint(raw_affiliation_strings.views.blueprint)
    app.register_blueprint(sdgs.views.blueprint)
    app.register_blueprint(sources.views.blueprint)
    app.register_blueprint(source_types.views.blueprint)
    app.register_blueprint(subfields.views.blueprint)
    app.register_blueprint(suggest.views.blueprint)
    app.register_blueprint(topics.views.blueprint)
    app.register_blueprint(vector_search.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(work_types.views.blueprint)
    return None


def register_extensions(app):
    db.init_app(app)
    sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), integrations=[FlaskIntegration()])
    connections.create_connection('default', hosts=[settings.ES_URL_WALDEN], timeout=15)
    connections.create_connection('walden', hosts=[settings.ES_URL_WALDEN], timeout=15)
    cache.init_app(app)


def register_errorhandlers(app):
    """Register error handlers."""

    def handle_exception(err):
        """Return custom JSON when APIError or its children are raised"""
        response = {"error": err.description, "message": ""}
        if len(err.args) > 0:
            response["message"] = err.args[0]
        # Add some logging so that we can monitor different types of errors
        app.logger.error("{}: {}".format(err.description, response["message"]))
        return jsonify(response), err.code

    app.errorhandler(APIError)(handle_exception)


if __name__ == '__main__':
    app = create_app()
    app.run()