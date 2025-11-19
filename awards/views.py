from flask import Blueprint, request

from awards.fields import fields_dict
from awards.schemas import AwardsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import process_only_fields

from settings import AWARDS_INDEX

blueprint = Blueprint("awards", __name__)


@blueprint.route("/awards")
def awards():
    # Awards data only exists in WALDEN connection, not in default/prod
    connection = 'walden'
    
    index_name = AWARDS_INDEX
    default_sort = ["id"]
    only_fields = process_only_fields(request, AwardsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
