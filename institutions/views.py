from flask import Blueprint, request

from core.shared_view import shared_view
from core.utils import is_cached
from extensions import cache
from institutions.fields import fields_dict
from institutions.schemas import MessageSchema

blueprint = Blueprint("institutions", __name__)


@blueprint.route("/institutions")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def institutions():
    index_name = "institutions-v3"
    default_sort = ["-works_count", "id"]
    result = shared_view(request, fields_dict, index_name, default_sort)
    message_schema = MessageSchema()
    return message_schema.dump(result)
