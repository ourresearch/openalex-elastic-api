import os

import sentry_sdk
from elasticsearch_dsl import connections
from flask import Flask, jsonify
from sentry_sdk.integrations.flask import FlaskIntegration

import authors
import autocomplete
import concepts
import continents
import countries
import counts
import domains
import fields
import funders
import ids
import institutions
import languages
import publishers
import settings
import sdgs
import sources
import source_types
import subfields
import suggest
import topics
import venues
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
    def add_header(response):
        response.cache_control.max_age = 60 * 60 * 1  # 1 hour
        return response

    return app


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(authors.views.blueprint)
    app.register_blueprint(autocomplete.views.blueprint)
    app.register_blueprint(concepts.views.blueprint)
    app.register_blueprint(continents.views.blueprint)
    app.register_blueprint(countries.views.blueprint)
    app.register_blueprint(counts.views.blueprint)
    app.register_blueprint(domains.views.blueprint)
    app.register_blueprint(fields.views.blueprint)
    app.register_blueprint(funders.views.blueprint)
    app.register_blueprint(ids.views.blueprint)
    app.register_blueprint(institutions.views.blueprint)
    app.register_blueprint(languages.views.blueprint)
    app.register_blueprint(publishers.views.blueprint)
    app.register_blueprint(sdgs.views.blueprint)
    app.register_blueprint(sources.views.blueprint)
    app.register_blueprint(source_types.views.blueprint)
    app.register_blueprint(subfields.views.blueprint)
    app.register_blueprint(suggest.views.blueprint)
    app.register_blueprint(topics.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(work_types.views.blueprint)
    app.register_blueprint(venues.views.blueprint)
    return None


def register_extensions(app):
    sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), integrations=[FlaskIntegration()])
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
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
