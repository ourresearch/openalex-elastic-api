from flask import Blueprint, jsonify, request, abort

from authors.fields import fields_dict
from authors.schemas import AuthorsSchema, MessageSchema
from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import (get_flattened_fields, get_valid_fields, process_only_fields)
from settings import AUTHORS_INDEX

blueprint = Blueprint("authors", __name__)


@blueprint.route("/authors")
@blueprint.route("/entities/authors")
@blueprint.route("/people")
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


@blueprint.route("/authors/valid_fields")
@blueprint.route("/people/valid_fields")
def authors_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/authors/flattened_schema")
@blueprint.route("/people/flattened_schema")
def authors_flattened_schema():
    flattened_schema = get_flattened_fields(AuthorsSchema())
    return jsonify(flattened_schema)

@blueprint.route("/authors/filters_docstrings")
@blueprint.route("/people/filters_docstrings")
def authors_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "authors",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/authors/config")
def authors_config():
    return jsonify(all_entities_config["authors"])
