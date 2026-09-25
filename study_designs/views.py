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
from study_designs.fields import fields_dict
from study_designs.schemas import StudyDesignsSchema, MessageSchema
from settings import STUDY_DESIGNS_INDEX

blueprint = Blueprint("study_designs", __name__)


@blueprint.route("/study-designs")
@blueprint.route("/entities/study-designs")
def study_designs():
    index_name = STUDY_DESIGNS_INDEX
    default_sort = ["-works_count", "id"]
    only_fields = process_only_fields(request, StudyDesignsSchema)
    result = shared_view(request, fields_dict, index_name, default_sort)
    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)
    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)


@blueprint.route("/study-designs/filters/<path:params>")
def study_designs_filters(params):
    index_name = STUDY_DESIGNS_INDEX
    results = shared_filter_view(request, params, fields_dict, index_name)
    filters_schema = FiltersWrapperSchema()
    return filters_schema.dump(results)


@blueprint.route("/study-designs/histogram/<string:param>")
def study_designs_histograms(param):
    index_name = STUDY_DESIGNS_INDEX
    result = shared_histogram_view(request, param, fields_dict, index_name)
    histogram_schema = HistogramWrapperSchema()
    return histogram_schema.dump(result)


@blueprint.route("/study-designs/valid_fields")
def study_designs_valid_fields():
    valid_fields = get_valid_fields(fields_dict)
    return jsonify(valid_fields)


@blueprint.route("/study-designs/flattened_schema")
def study_designs_flattened_schema():
    flattened_schema = get_flattened_fields(StudyDesignsSchema())
    return jsonify(flattened_schema)


@blueprint.route("/study-designs/filters_docstrings")
def study_designs_filters_doctrings():
    ret = {}
    for param, f in fields_dict.items():
        ret[param] = {
            "key": f.param,
            "entityType": "study-designs",
            "docstring": f.docstring,
            "documentationLink": f.documentation_link,
            "alternateNames": f.alternate_names,
        }
    return jsonify(ret)


@blueprint.route("/study-designs/config")
def study_designs_config():
    return jsonify(all_entities_config["study-designs"])
