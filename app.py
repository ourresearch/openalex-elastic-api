from elasticsearch_dsl import connections
from flask import Flask

import settings
import works
from works.api_spec import spec


def create_app(config_object="settings"):
    app = Flask(__name__)
    app.config.from_object(config_object)
    register_blueprints(app)
    register_extensions(app)
    return app


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(works.views.blueprint)
    return None


def register_extensions(app):
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    with app.test_request_context():
        spec.path(view=works.views.works)
        spec.path(view=works.views.detail)
