import json
from collections import OrderedDict

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from flask import Blueprint, abort, render_template, request

import settings
from works.api_spec import spec
from works.schemas import WorksSchema
from works.search import filter_records, group_by_records, search_records
from works.utils import map_query_params

blueprint = Blueprint("works", __name__, static_folder="../static")


@blueprint.route("/")
def index():
    """
    ---
    get:
      description: Search and filter works
      responses:
        200:
          description: Return works
          content:
            application/json:
              schema: WorksSchema
    """
    details = request.args.get("details")
    filters = map_query_params(request.args.get("filter"))
    group_by = request.args.get("group_by")
    search_params = map_query_params(request.args.get("search"))

    if details == "true":
        s = Search(using=Elasticsearch(settings.ES_URL), index="works-*").params(
            request_timeout=30
        )
    else:
        s = (
            Search(using=Elasticsearch(settings.ES_URL), index="works-*")
            .params(request_timeout=30)
            .extra(from_=0, size=0)
        )

    # guard rails
    if (
        group_by
        and filters
        and "year" in filters
        and (group_by == "author_id" or group_by == "issn")
        and ("<" in filters["year"] or ">" in filters["year"])
        and len(filters) == 1
        and not search_params
    ):
        # do not allow query like /?year>2000&group_by=author_id
        abort(404, description="Not allowed")

    # filter
    s = filter_records(filters, s)

    # search
    s = search_records(search_params, s)

    # group by
    s = group_by_records(group_by, s)

    response = s.execute()

    result = OrderedDict()
    result["meta"] = {"hits": s.count(), "response_time": response.took}

    if group_by == "author_id":
        result["group_by"] = sorted(
            [
                item.to_dict()
                for item in response.aggregations.affiliations.groupby.buckets
            ],
            key=lambda item: item["key"],
        )
    elif group_by == "issn":
        result["group_by"] = sorted(
            [item.to_dict() for item in response.aggregations.groupby.buckets],
            key=lambda item: item["key"],
        )
    elif group_by:
        result["group_by"] = sorted(
            [item.to_dict() for item in response.aggregations.groupby.buckets],
            key=lambda item: item["key"],
            reverse=True,
        )
    works_schema = WorksSchema(many=True)
    result["results"] = works_schema.dump(response)
    return result


@blueprint.route("/openapi_json")
def openapi_json():
    return json.dumps(spec.to_dict(), indent=2)


@blueprint.route("/docs")
def docs():
    return render_template("redoc.html")
