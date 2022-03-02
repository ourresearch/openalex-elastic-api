from flask import Blueprint, jsonify, request

from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from settings import WORKS_INDEX
from works.fields import fields_dict
from works.schemas import MessageSchema

blueprint = Blueprint("works", __name__)


@blueprint.route("/")
def index():
    return jsonify(
        {
            "version": "0.1",
            "documentation_url": "/docs",
            "msg": "Don't panic",
        }
    )


@blueprint.route("/works")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def works():
    index_name = WORKS_INDEX
    default_sort = ["-publication_date"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)


@blueprint.route("/works/filters/<path:params>")
def works_filters(params):
    index_name = WORKS_INDEX
    results = shared_filter_view(params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)
