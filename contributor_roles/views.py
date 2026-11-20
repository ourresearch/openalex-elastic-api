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
from contributor_roles.fields import fields_dict
from contributor_roles.schemas import ContributorRolesSchema, MessageSchema
from settings import CONTRIBUTOR_ROLES_INDEX

blueprint = Blueprint("contributor_roles", __name__)


@blueprint.route("/contributor-roles")
@blueprint.route("/entities/contributor-roles")
def contributor_roles():
    index_name = CONTRIBUTOR_ROLES_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, ContributorRolesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/contributor-roles/filters/<path:params>")
def contributor_roles_filters(params):
    index_name = CONTRIBUTOR_ROLES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/contributor-roles/histogram/<string:param>")
def contributor_roles_histograms(param):
    index_name = CONTRIBUTOR_ROLES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/contributor-roles/valid_fields")
def contributor_roles_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/contributor-roles/flattened_schema")
def contributor_roles_flattened_schema():
    flattened_schema = get_flattened_fields(ContributorRolesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/contributor-roles/filters_docstrings")
def contributor_roles_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "contributor-roles",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/contributor-roles/config")
def contributor_roles_config():
    return jsonify(all_entities_config["contributor-roles"])
