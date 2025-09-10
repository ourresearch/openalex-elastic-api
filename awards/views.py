from flask import Blueprint, request, abort

from awards.fields import fields_dict
from awards.schemas import AwardsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields
from core.schemas import process_id_only_fields
from extensions import cache
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections

blueprint = Blueprint("awards", __name__)

AWARDS_INDEX = "awards-v1"


@blueprint.route("/awards")
@blueprint.route("/v2/awards")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def awards():
    index_name = AWARDS_INDEX
    default_sort = ["native_id", "id"]
    only_fields = process_only_fields(request, AwardsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='walden')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/awards/<path:id>")
@blueprint.route("/v2/awards/<path:id>")
def awards_id_get(id):
    """Get a specific award by ID"""
    s = Search(index=AWARDS_INDEX, using='walden')
    only_fields = process_id_only_fields(request, AwardsSchema)

    query = {"term": {"id": id}}
    s = s.filter(query)
    
    client = connections.get_connection('walden')
    response = s.execute()
    
    if not response or len(response) == 0:
        abort(404)
    
    awards_schema = AwardsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return awards_schema.dump(response[0])
