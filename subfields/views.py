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
    is_cached,
    process_only_fields,
)
from extensions import cache
from subfields.fields import fields_dict
from subfields.schemas import SubfieldsSchema, MessageSchema
from settings import SUBFIELDS_INDEX

blueprint = Blueprint("subfields", __name__)


@blueprint.route("/subfields")
@blueprint.route("/entities/subfields")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def subfields():
    index_name = SUBFIELDS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, SubfieldsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/subfields/filters/<path:params>")
def subfields_filters(params):
    index_name = SUBFIELDS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/subfields/histogram/<string:param>")
def subfields_histograms(param):
    index_name = SUBFIELDS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/subfields/valid_fields")
def subfields_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/subfields/flattened_schema")
def subfields_flattened_schema():
    flattened_schema = get_flattened_fields(SubfieldsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/subfields/filters_docstrings")
def subfields_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "subfields",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/subfields/config")
def subfields_config():
    return jsonify(all_entities_config["subfields"])
