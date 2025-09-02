from flask import Blueprint, jsonify, request

from combined_config import all_entities_config
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.histogram import shared_histogram_view
from core.schemas import (FiltersWrapperSchema, HistogramWrapperSchema,
                          StatsWrapperSchema)
from core.shared_view import shared_view
from core.stats_view import shared_stats_view
from core.utils import (get_flattened_fields, get_valid_fields, is_cached,
                        process_only_fields)
from extensions import cache
from institutions.fields import fields_dict
from institutions.schemas import InstitutionsSchema, MessageSchema
from settings import INSTITUTIONS_INDEX

blueprint = Blueprint("institutions", __name__)


@blueprint.route("/institutions")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def institutions():
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, InstitutionsSchema)
    
    # Check data_version parameter to determine connection
    data_version = request.args.get('data_version') or request.args.get('data-version', '1')
    connection = 'walden' if data_version == '2' else 'default'
    
    result = shared_view(request, fields_dict, INSTITUTIONS_INDEX, default_sort, connection)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/institutions/filters/<path:params>")
def institutions_filters(params):
    index_name = INSTITUTIONS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/institutions/stats/")
def institutions_stats():
    stats_fields = ["cited_by_count", "works_count"]
    index_name = INSTITUTIONS_INDEX
    entity_name = "institutions"
    result = shared_stats_view(
        request, fields_dict, index_name, stats_fields, entity_name
    )
    stats_schema = StatsWrapperSchema()
    return stats_schema.dump(result)


@blueprint.route("/institutions/histogram/<string:param>")
def institutions_histograms(param):
    index_name = INSTITUTIONS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/institutions/valid_fields")
def institutions_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/institutions/flattened_schema")
def institutions_flattened_schema():
    flattened_schema = get_flattened_fields(InstitutionsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/institutions/filters_docstrings")
def institutions_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "institutions",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/v2/institutions")
def v2_institutions():
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, InstitutionsSchema)
    result = shared_view(request, fields_dict, INSTITUTIONS_INDEX, default_sort, connection='walden')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/institutions/config")
def institutions_config():
    return jsonify(all_entities_config["institutions"])
