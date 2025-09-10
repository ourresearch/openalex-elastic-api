from flask import Blueprint, request

from awards.fields import fields_dict
from awards.schemas import AwardsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields
from extensions import cache

blueprint = Blueprint("awards", __name__)

AWARDS_INDEX = "awards-v1"


@blueprint.route("/awards")
@blueprint.route("/v2/awards")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def awards():
    index_name = AWARDS_INDEX
    default_sort = ["id"]
    only_fields = process_only_fields(request, AwardsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='walden')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
