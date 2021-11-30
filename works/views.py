import json
from collections import OrderedDict

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from flask import Blueprint, abort, render_template, request

import settings
from works.api_spec import spec
from works.schemas import GroupBySchema, WorksSchema
from works.search import filter_records, group_by_records, search_records
from works.utils import map_query_params

blueprint = Blueprint("works", __name__)


@blueprint.route("/works")
def index():
    """
    ---
    get:
      description: Filter, search, and group works records.
      parameters:
      - in: query
        name: filter
        style: deepObject
        explode: false
        schema:
          type: object
          description: Filter works with a list of filters in format works/?filter=year:2020,ror_id=03vek6s52
          properties:
            issn:
              type: string
              description: filter by journal issn
            ror_id:
              type: string
              description: filter by ROR ID
            year:
              type: int
              description: filter by publication year with exact (filter=year:2020), less than (filter=year:<2020)
                or greater than (filter=year:>2020)
      - in: query
        name: search
        style: deepObject
        explode: false
        schema:
          type: object
          description: Search works in format works/?search=title:covid-19,publisher:elsevier
          properties:
            author:
              type: string
              description: search by author name
            journal_title:
              type: string
              description: search by journal title
            publisher:
              type: string
              description: search by publisher name
            title:
              type: string
              description: search by works title
      - in: query
        schema: WorksQuerySchema
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

    s = Search(index="works-*")

    if details != "true":
        s = s.extra(size=0)

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

    group_by_schema = GroupBySchema(many=True)
    if group_by == "author_id":
        result["group_by"] = group_by_schema.dump(
            response.aggregations.affiliations.groupby.buckets
        )
    elif group_by == "issn":
        result["group_by"] = group_by_schema.dump(response.aggregations.groupby.buckets)
    elif group_by:
        result["group_by"] = group_by_schema.dump(response.aggregations.groupby.buckets)
    works_schema = WorksSchema(many=True)
    result["results"] = works_schema.dump(response)
    return result


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
