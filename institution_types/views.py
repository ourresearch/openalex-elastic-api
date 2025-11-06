from flask import Blueprint, jsonify, request

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
from institution_types.fields import fields_dict
from institution_types.schemas import InstitutionTypesSchema, MessageSchema
from settings import INSTITUTION_TYPES_INDEX

blueprint = Blueprint("institution_types", __name__)


@blueprint.route("/institution-types")
@blueprint.route("/entities/institution-types")
def institution_types():
    index_name = INSTITUTION_TYPES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, InstitutionTypesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/institution-types/filters/<path:params>")
def institution_types_filters(params):
    index_name = INSTITUTION_TYPES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/institution-types/histogram/<string:param>")
def institution_types_histograms(param):
    index_name = INSTITUTION_TYPES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/institution-types/valid_fields")
def institution_types_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/institution-types/flattened_schema")
def institution_types_flattened_schema():
    flattened_schema = get_flattened_fields(InstitutionTypesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/institution-types/filters_docstrings")
def institution_types_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "types",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)
