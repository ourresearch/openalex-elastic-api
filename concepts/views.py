from flask import Blueprint, jsonify, request

from concepts.fields import fields_dict
from concepts.schemas import ConceptsSchema, MessageSchema
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import (get_flattened_fields, get_valid_fields, is_cached,
                        process_only_fields)
from extensions import cache
from settings import CONCEPTS_INDEX

blueprint = Blueprint("concepts", __name__)


@blueprint.route("/concepts")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def concepts():
    index_name = CONCEPTS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, ConceptsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/concepts/filters/<path:params>")
def concepts_filters(params):
    index_name = CONCEPTS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/concepts/valid_fields")
def concepts_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/concepts/flattened_schema")
def concepts_flattened_schema():
    flattened_schema = get_flattened_fields(ConceptsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/concepts/filters_docstrings")
def concepts_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "concepts",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
        }
    return jsonify(ret)