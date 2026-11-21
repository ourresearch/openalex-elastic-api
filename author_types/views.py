from flask import Blueprint, jsonify, request

from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import FiltersWrapperSchema, HistogramWrapperSchema
from core.shared_view import shared_view
from core.utils import (
    get_flattened_fields,
    get_valid_fields,
    process_only_fields,
)
from author_types.fields import fields_dict
from author_types.schemas import AuthorTypesSchema, MessageSchema
from settings import AUTHOR_TYPES_INDEX

# oxjob #2437: what kind of agent an author is (human, organization, software-agent). Index
# author-types-v1 is built by walden, as work-relationships-v1 is for /relationships.
blueprint = Blueprint("author_types", __name__)


@blueprint.route("/author-types")
@blueprint.route("/entities/author-types")
def author_types():
    index_name = AUTHOR_TYPES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, AuthorTypesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/author-types/filters/<path:params>")
def author_types_filters(params):
    index_name = AUTHOR_TYPES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/author-types/histogram/<string:param>")
def author_types_histograms(param):
    index_name = AUTHOR_TYPES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/author-types/valid_fields")
def author_types_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/author-types/flattened_schema")
def author_types_flattened_schema():
    flattened_schema = get_flattened_fields(AuthorTypesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/author-types/filters_docstrings")
def author_types_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "author-types",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/author-types/config")
def author_types_config():
    return jsonify(all_entities_config["author-types"])
