from flask import Blueprint, jsonify, request

from core.export import export_group_by, is_group_by_export
from core.shared_view import shared_view
from core.utils import get_flattened_fields, get_valid_fields, is_cached, process_only_fields
from extensions import cache

blueprint = Blueprint("funder_search", __name__)

# Import after blueprint definition to avoid circular imports
from funder_search.fields import fields_dict
from funder_search.schemas import FunderSearchSchema, MessageSchema

INDEX_NAME = "funder-search"


@blueprint.route("/funder-search")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def funder_search():
    # Search works index on default connection
    import settings
    connection = 'default'
    index_name = settings.WORKS_INDEX
    default_sort = ["_score", "publication_date", "id"]

    only_fields = process_only_fields(request, FunderSearchSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection)

    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)

    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
