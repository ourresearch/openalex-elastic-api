from collections import OrderedDict

from elasticsearch_dsl import Search
from flask import Blueprint, current_app, jsonify, request

from core.exceptions import APIError, APIQueryParamsError
from core.filter import filter_records
from core.group_by import group_by_records
from core.paginate import Paginate
from core.sort import sort_records
from core.utils import get_field, map_filter_params, map_sort_params
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
    filter_params = map_filter_params(request.args.get("filter"))
    group_by = request.args.get("group_by")
    group_by_size = request.args.get("group-by-size", 50, type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per-page", 25, type=int)
    sort_params = map_sort_params(request.args.get("sort"))

    paginate = Paginate(page, per_page)
    paginate.validate()

    s = Search(index="works-v4-*,-*invalid-data")

    if group_by:
        s = s.extra(size=0)
    else:
        s = s.extra(size=per_page)

    # filter
    if filter_params:
        s = filter_records(fields_dict, filter_params, s)

    if filter_params and (
        "title.search" in filter_params.keys()
        or "display_name.search" in filter_params.keys()
        or "display_name" in filter_params.keys()
    ):
        is_search_query = True
    else:
        is_search_query = False

    # sort
    if sort_params and not is_search_query:
        s = sort_records(fields_dict, group_by, sort_params, s)
    elif is_search_query and not sort_params:
        s = s.sort("_score")
    elif not group_by:
        s = s.sort("-publication_date")

    # group by
    if group_by:
        field = get_field(fields_dict, group_by)
        if (
            field.is_date_query
            or field.is_range_query
            and field.param != "publication_year"
        ):
            raise APIQueryParamsError("Cannot group by date or number fields.")
        s = group_by_records(field, group_by_size, s, sort_params)

    if not group_by:
        response = s[paginate.start : paginate.end].execute()
    else:
        response = s.execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": page,
        "per_page": group_by_size if group_by else per_page,
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


@blueprint.route("/complete")
def complete():
    q = request.args.get("q")
    s = Search(index="works-v2-*,-*invalid-data")
    s = s.suggest("title_suggestion", q, completion={"field": "display_name.complete"})
    response = s.execute()
    title_results = [r.text for r in response.suggest.title_suggestion[0].options]
    return jsonify(title_results)


@blueprint.errorhandler(APIError)
def handle_exception(err):
    """Return custom JSON when APIError or its children are raised"""
    response = {"error": err.description, "message": ""}
    if len(err.args) > 0:
        response["message"] = err.args[0]
    # Add some logging so that we can monitor different types of errors
    current_app.logger.error("{}: {}".format(err.description, response["message"]))
    return jsonify(response), err.code
