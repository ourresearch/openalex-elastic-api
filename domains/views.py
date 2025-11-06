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
from domains.fields import fields_dict
from domains.schemas import DomainsSchema, MessageSchema
from settings import DOMAINS_INDEX

blueprint = Blueprint("domains", __name__)


@blueprint.route("/domains")
@blueprint.route("/entities/domains")
def domains():
    index_name = DOMAINS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, DomainsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/domains/filters/<path:params>")
def domains_filters(params):
    index_name = DOMAINS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/domains/histogram/<string:param>")
def domains_histograms(param):
    index_name = DOMAINS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/domains/valid_fields")
def domains_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/domains/flattened_schema")
def domains_flattened_schema():
    flattened_schema = get_flattened_fields(DomainsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/domains/filters_docstrings")
def domains_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "domains",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/domains/config")
def domains_config():
    return jsonify(all_entities_config["domains"])
