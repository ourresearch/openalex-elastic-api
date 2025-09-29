import os

import sentry_sdk
from elasticsearch_dsl import connections
from flask import Flask, jsonify
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
import funders
import ids
import institution_types
import institutions
import keywords
import languages
import licenses
import locations
import oql
import publishers
import settings
import sdgs
import sources
import source_types
import subfields
import suggest
import topics
import works
import work_types
from core.exceptions import APIError
from extensions import cache, compress, db


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
    def add_header(response):
        response.cache_control.max_age = 60 * 60 * 24 * 1  # 1 day
        return response

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response

    @app.route('/.well-known/acme-challenge/zGivZHe7yjlRfYmLpJXeUY3MuVXk1rrCbeCwI2cN2EVZ_wpF7B1u9Wv3Z06kF4x0')
    def acme_challenge():
        return 'zGivZHe7yjlRfYmLpJXeUY3MuVXk1rrCbeCwI2cN2EVZ_wpF7B1u9Wv3Z06kF4x0.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'

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
    app.register_blueprint(funders.views.blueprint)
    app.register_blueprint(ids.views.blueprint)
    app.register_blueprint(institution_types.views.blueprint)
    app.register_blueprint(institutions.views.blueprint)
    app.register_blueprint(keywords.views.blueprint)
    app.register_blueprint(languages.views.blueprint)
    app.register_blueprint(licenses.views.blueprint)
    app.register_blueprint(locations.views.blueprint)
    app.register_blueprint(oql.views.blueprint)
    app.register_blueprint(publishers.views.blueprint)
    app.register_blueprint(sdgs.views.blueprint)
    app.register_blueprint(sources.views.blueprint)
    app.register_blueprint(source_types.views.blueprint)
    app.register_blueprint(subfields.views.blueprint)
    app.register_blueprint(suggest.views.blueprint)
    app.register_blueprint(topics.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(work_types.views.blueprint)
    return None


def register_extensions(app):
    db.init_app(app)
    sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), integrations=[FlaskIntegration()])
    connections.create_connection('default', hosts=[settings.ES_URL], timeout=30)
    if settings.ES_URL_WALDEN:
        connections.create_connection('walden', hosts=[settings.ES_URL_WALDEN], timeout=30)
    cache.init_app(app)
    compress.init_app(app)


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