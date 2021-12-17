import json
from collections import OrderedDict

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from flask import Blueprint, current_app, jsonify, render_template, request

import settings
from works.api_spec import spec
from works.exceptions import APIError
from works.schemas import MessageSchema, WorksSchema
from works.search import filter_records, group_by_records, search_records
from works.utils import convert_group_by, map_query_params
from works.validate import (validate_params, validate_per_page,
                            validate_result_size)

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

    # validate
    validate_params(filter_params, group_by, search)
    validate_result_size(page, per_page)

    query_type = None

    if (
        group_by
        and group_by == "author_id"
        and filter_params
        and "year" in filter_params
        and len(filter_params) == 1
        and not search
    ):
        s = Search(index="transform-author-id-by-year")
        query_type = "author_id_by_year"
    elif (
        group_by
        and group_by == "issn"
        and filter_params
        and "year" in filter_params
        and len(filter_params) == 1
        and not search
    ):
        s = Search(index="transform-issns-by-year")
        query_type = "issns_by_year"
    else:
        s = Search(index="works-v2-*,-*invalid-data")

    if not group_by:
        s = s.extra(size=per_page)
    elif query_type:
        s = s.extra(size=10)
    else:
        s = s.extra(size=0)

    # filter
    if filter_params:
        s = filter_records(filter_params, s)

    # search
    s = search_records(search, s)

    # group by
    s = group_by_records(group_by, s, group_by_size, query_type)

    # sort
    if search:
        s = s.sort("_score")
    elif (
        not group_by
        and search
        or filter_params
        and not ("year" in filter_params and len(filter_params) == 1)
    ):
        s = s.sort("-publication_date")

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
    if group_by == "country":
        result["group_by"] = response.aggregations.affiliations.groupby.buckets
    elif group_by and query_type == "author_id_by_year":
        result["group_by"] = convert_group_by(response, "author_id")
    elif group_by and query_type == "issns_by_year":
        result["group_by"] = convert_group_by(response, "issn")
    elif group_by:
        result["group_by"] = response.aggregations.groupby.buckets
    else:
        result["group_by"] = []
        result["results"] = response
    message_schema = MessageSchema()
    print(s.to_dict())
    return message_schema.dump(result)


@blueprint.route("/work/<work_id>")
def detail(work_id):
    """
    ---
    get:
      description: Retrieve a single work.
      parameters:
      - in: path
        name: id
        schema:
          type: string
          required: true
      responses:
        200:
          description: Return a single work
          content:
            application/json:
              schema: WorksSchema
    """
    s = Search(using=Elasticsearch(settings.ES_URL), index="works-*").params(
        request_timeout=30
    )
    s = s.filter("term", paper_id=work_id)
    response = s.execute()
    works_schema = WorksSchema()
    return works_schema.dump(response)


@blueprint.route("/openapi_json")
def openapi_json():
    return json.dumps(spec.to_dict(), indent=2)


@blueprint.route("/docs")
def docs():
    return render_template("redoc.html")


@blueprint.errorhandler(APIError)
def handle_exception(err):
    """Return custom JSON when APIError or its children are raised"""
    response = {"error": err.description, "message": ""}
    if len(err.args) > 0:
        response["message"] = err.args[0]
    # Add some logging so that we can monitor different types of errors
    current_app.logger.error("{}: {}".format(err.description, response["message"]))
    return jsonify(response), err.code
