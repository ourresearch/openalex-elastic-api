from flask import Blueprint, request

from awards.fields import fields_dict
from awards.schemas import AwardsSchema, MessageSchema
from core.shared_view import shared_view
from core.utils import process_only_fields

from settings import AWARDS_INDEX

blueprint = Blueprint("awards", __name__)

# The default order: newest start year first, then most funded outputs, then id (oxjob #2168).
# Every award from a funder's own registry has a start year; the blank ones minted from paper
# funding notes ("HORIZON2020") have none, and a desc sort puts them last. The OQL execution
# path reads this list (query_translation/execution.py); oql_core._THINGS_DEFAULT_SORT names
# its first key for the sort menu.
DEFAULT_SORT = ["-start_year", "-funded_outputs_count", "id"]


@blueprint.route("/awards")
def awards():
    # Awards data only exists in WALDEN connection, not in default/prod
    connection = 'walden'
    
    index_name = AWARDS_INDEX
    default_sort = DEFAULT_SORT
    only_fields = process_only_fields(request, AwardsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
