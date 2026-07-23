import json
import os
import time

import sentry_sdk
from elasticsearch_dsl import connections
from flask import Flask, jsonify, request
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
import changefiles
import snapshots
import sources
import source_types
import subfields
import suggest
import topics
import works
import work_types
from core.exceptions import APIError
from extensions import cache


def create_app(config_object="settings"):
    app = Flask(__name__)
    app.config.from_object(config_object)

    register_blueprints(app)
    register_extensions(app)
    register_errorhandlers(app)

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response

    @app.after_request
    def inject_cost_usd(response):
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
    app.register_blueprint(changefiles.views.blueprint)
    app.register_blueprint(snapshots.views.blueprint)
    app.register_blueprint(sources.views.blueprint)
    app.register_blueprint(source_types.views.blueprint)
    app.register_blueprint(subfields.views.blueprint)
    app.register_blueprint(suggest.views.blueprint)
    app.register_blueprint(topics.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(work_types.views.blueprint)
    return None


def register_extensions(app):
    sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), integrations=[FlaskIntegration()])
    # oxjob #521: ES client timeout 15s -> 7s. The query timeout is a soft 5s
    # (returns partial), so a 15s client wait just pins a Heroku worker on doomed
    # queries long after the proxy (9s) gave up, exhausting workers -> H12s. 7s lets
    # the worker return cleanly just after the 5s query budget. (vector left at 15s:
    # semantic search legitimately runs longer and isn't part of the works-search load.)
    connections.create_connection('default', hosts=[settings.ES_URL_WALDEN], timeout=7)
    connections.create_connection('walden', hosts=[settings.ES_URL_WALDEN], timeout=7)
    if settings.ES_VECTOR_SEARCH_URL:
        connections.create_connection('vector', hosts=[settings.ES_VECTOR_SEARCH_URL], timeout=15)
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
        headers = {}
        # 503s get a Retry-After hint so polite clients back off rather than
        # hammering during a users-api blip (security review M5).
        if err.code == 503:
            headers["Retry-After"] = "30"
        return jsonify(response), err.code, headers

    app.errorhandler(APIError)(handle_exception)


if __name__ == '__main__':
    app = create_app()
    app.run()