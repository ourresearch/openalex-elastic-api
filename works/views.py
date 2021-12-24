from collections import OrderedDict

from elasticsearch_dsl import Search
from flask import Blueprint, current_app, jsonify, request

from core.exceptions import APIError
from core.filter import filter_records
from core.search import search_records
from core.sort import sort_records
from core.utils import map_query_params
from core.validate import (validate_params, validate_per_page,
                           validate_result_size)
from works.fields import fields_dict
from works.schemas import MessageSchema

blueprint = Blueprint("works", __name__)


@blueprint.route("/")
def index():
    return jsonify(
        {
            "version": "0.1",
            "documentation_url": "/docs",
            "msg": "Don't panic",
        }
    )


@blueprint.route("/works")
def works():
    filter_params = map_query_params(request.args.get("filter"))
    group_by = request.args.get("group_by")
    group_by_size = request.args.get("group-by-size", 50, type=int)
    page = request.args.get("page", 1, type=int)
    per_page = validate_per_page(request.args.get("per-page", 10, type=int))
    search = request.args.get("search")
    sort_params = map_query_params(request.args.get("sort"))

    # validate
    validate_params(filter_params, group_by, search)
    validate_result_size(page, per_page)

    s = Search(index="works-v2-*,-*invalid-data")

    if group_by:
        s = s.extra(size=0)
    else:
        s = s.extra(size=per_page)

    # search
    s = search_records(search, s)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    # sort
    # if search and sort_params:
    #     s = sort_records(sort_params, s)
    if sort_params and not search:
        s = sort_records(fields_dict, sort_params, s)
    elif search and not sort_params:
        s = s.sort("_score")
    elif (
        not group_by
        and search
        or filter_params
        and not ("publication_year" in filter_params and len(filter_params) == 1)
    ):
        s = s.sort("-publication_date")

    # group by
    # s = group_by_records(group_by, s, group_by_size, query_type)

    # paginate
    start = 0 if page == 1 else (per_page * page) - per_page + 1
    end = per_page * page

    if not group_by:
        response = s[start:end].execute()
    else:
        response = s.execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "response_time": response.took,
        "page": page,
        "per_page": per_page,
    }

    result["results"] = []
    if group_by:
        result["group_by"] = response.aggregations.groupby.buckets
    else:
        result["group_by"] = []
        result["results"] = response
    message_schema = MessageSchema()
    print(s.to_dict())
    return message_schema.dump(result)


@blueprint.errorhandler(APIError)
def handle_exception(err):
    """Return custom JSON when APIError or its children are raised"""
    response = {"error": err.description, "message": ""}
    if len(err.args) > 0:
        response["message"] = err.args[0]
    # Add some logging so that we can monitor different types of errors
    current_app.logger.error("{}: {}".format(err.description, response["message"]))
    return jsonify(response), err.code
