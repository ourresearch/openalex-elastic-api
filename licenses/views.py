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
from licenses.fields import fields_dict
from licenses.schemas import LicensesSchema, MessageSchema
from settings import LICENSES_INDEX

blueprint = Blueprint("licenses", __name__)

DISPLAY_NAMES = {
    "cc-by": "CC-BY",
    "cc-by-sa": "CC-BY-SA",
    "cc-by-nc": "CC-BY-NC",
    "cc-by-nc-sa": "CC-BY-NC-SA",
    "cc-by-nd": "CC-BY-ND",
    "cc-by-nc-nd": "CC-BY-NC-ND",
}

DESCRIPTIONS = {
    "cc-by": "Reuse allowed with credit to the creator, including commercial use.",
    "cc-by-sa": "Reuse with credit, including commercial use, but adaptations must keep the same license.",
    "cc-by-nc": "Reuse with credit for non-commercial purposes only.",
    "cc-by-nc-sa": "Reuse with credit for non-commercial purposes; adaptations must keep the same license.",
    "cc-by-nd": "Sharing with credit, including commercial use, but no adaptations.",
    "cc-by-nc-nd": "Sharing with credit, but no commercial use and no adaptations.",
    "public-domain": "No rights reserved; the work is in the public domain with no restrictions on reuse.",
    "other-oa": "A license that looks open but we don't have it listed anywhere.",
    "mit": "A simple permissive license requiring only copyright notice preservation.",
    "apache-2-0": "A permissive license requiring copyright notices and providing patent rights.",
    "gpl-v3": "A copyleft license requiring that modified versions also be open-source under the same terms.",
    "isc": "A permissive license functionally equivalent to MIT and BSD 2-Clause.",
}


def inject_overrides(results):
    for item in results:
        short_id = item.get("id", "").split("/")[-1]
        if short_id in DISPLAY_NAMES:
            item["display_name"] = DISPLAY_NAMES[short_id]
        if short_id in DESCRIPTIONS:
            item["description"] = DESCRIPTIONS[short_id]


@blueprint.route("/licenses")
@blueprint.route("/entities/licenses")
def licenses():
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, LicensesSchema)
    result = shared_view(request, fields_dict, LICENSES_INDEX, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    dumped = message_schema.dump(result)
    inject_overrides(dumped["results"])
    return dumped


@blueprint.route("/licenses/filters/<path:params>")
def licenses_filters(params):
    index_name = LICENSES_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/licenses/histogram/<string:param>")
def licenses_histograms(param):
    index_name = LICENSES_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/licenses/valid_fields")
def licenses_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/licenses/flattened_schema")
def licenses_flattened_schema():
    flattened_schema = get_flattened_fields(LicensesSchema())
    return jsonify(flattened_schema)


@blueprint.route("/licenses/filters_docstrings")
def licenses_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "licenses",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/v2/licenses")
def v2_licenses():
    index_name = "licenses-v1"
    default_sort = ["id"]
    only_fields = process_only_fields(request, LicensesSchema)
    result = shared_view(request, fields_dict, index_name, default_sort, connection='v2')
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/licenses/config")
def licenses_config():
    return jsonify(all_entities_config["licenses"])
