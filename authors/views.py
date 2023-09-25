from flask import Blueprint, jsonify, request

from authors.fields import fields_dict
from authors.schemas import AuthorsSchema, MessageSchema
from core.export import export_group_by, is_group_by_export
from core.filters_view import shared_filter_view
from core.schemas import FiltersWrapperSchema
from core.shared_view import shared_view
from core.utils import (get_flattened_fields, get_valid_fields, is_cached,
                        process_only_fields)
from extensions import cache
from settings import AUTHORS_INDEX

blueprint = Blueprint("authors", __name__)


# Old Author IDs are fully deprecated, so the below is commented out
# def is_query_for_old_authors():
#     # backwards compatability check. returns True if all of the author IDs requested are old authors
#     from core.utils import get_index_name_by_id, map_filter_params

#     filter_params = map_filter_params(request.args.get("filter"))
#     if filter_params:
#         fields_to_check = ["openalex", "openalex_id"]
#         index_list = []
#         for filter in filter_params:
#             for key, value in filter.items():
#                 if key in fields_to_check:
#                     openalex_ids = value.split("|")
#                     for openalex_id in openalex_ids:
#                         index_list.append(get_index_name_by_id(openalex_id))
#         if index_list and all(
#             [index_name == AUTHORS_INDEX_OLD for index_name in index_list]
#         ):
#             return True
#     return False


@blueprint.route("/authors")
@blueprint.route("/people")
@cache.cached(
    timeout=24 * 60 * 60, query_string=True, unless=lambda: not is_cached(request)
)
def authors():
    index_name = AUTHORS_INDEX
    # if is_query_for_old_authors() is True:
    #     index_name = AUTHORS_INDEX_OLD
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
        }
    return jsonify(ret)