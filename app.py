import os

import sentry_sdk
from elasticsearch_dsl import connections
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration

import authors
import settings
import venues
import works


def create_app(config_object="settings"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    register_blueprints(app)
    register_extensions(app)
    return app


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(authors.views.blueprint)
    app.register_blueprint(works.views.blueprint)
    app.register_blueprint(venues.views.blueprint)
    return None


def register_extensions(app):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.5,
    )
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
