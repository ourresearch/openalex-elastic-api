from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin

spec = APISpec(
    title="OpenAlex works API",
    version="0.1.0",
    openapi_version="3.0.2",
    info=dict(description="OpenAlex works API Documentation"),
    plugins=[FlaskPlugin(), MarshmallowPlugin()],
)
