from flask import Blueprint, request

from authors.fields import fields_dict
from authors.schemas import AuthorsSchema, MessageSchema
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import is_cached, process_only_fields
from extensions import cache
from settings import AUTHORS_INDEX

blueprint = Blueprint("authors", __name__)


@blueprint.route("/authors")
@blueprint.route("/people")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def authors():
    index_name = AUTHORS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, AuthorsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/authors/filters/<path:params>")
@blueprint.route("/people/filters/<path:params>")
def authors_filters(params):
    index_name = AUTHORS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)
