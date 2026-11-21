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
from link_types.fields import fields_dict
from link_types.schemas import LinkTypesSchema, MessageSchema
from settings import LINK_TYPES_INDEX

# oxjob #2481: the kinds of link between two works (citation, review, volume, component, data-series, part), the new
# name of /relationships. Both answer until the cutover; walden writes the same records to both indexes.
blueprint = Blueprint("link_types", __name__)


@blueprint.route("/link-types")
@blueprint.route("/entities/link-types")
def link_types():
    index_name = LINK_TYPES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, LinkTypesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/link-types/filters/<path:params>")
def link_types_filters(params):
    index_name = LINK_TYPES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/link-types/histogram/<string:param>")
def link_types_histograms(param):
    index_name = LINK_TYPES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/link-types/valid_fields")
def link_types_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/link-types/flattened_schema")
def link_types_flattened_schema():
    flattened_schema = get_flattened_fields(LinkTypesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/link-types/filters_docstrings")
def link_types_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "link-types",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/link-types/config")
def link_types_config():
    return jsonify(all_entities_config["link-types"])
