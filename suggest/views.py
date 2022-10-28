from collections import OrderedDict

from elasticsearch_dsl import Search
from flask import Blueprint, request

from core.exceptions import APIQueryParamsError
from suggest.schemas import SuggestMessageSchema

blueprint = Blueprint("suggest", __name__)


@blueprint.route("/suggest")
def suggest():
    if "q" not in request.args:
        raise APIQueryParamsError(
            f"Must enter a 'q' parameter in order to use suggestions. Example: {request.url_rule}?q=training"
        )
    q = request.args.get("q")
    result = OrderedDict()
    if q:
        s = Search(index="suggest-v1")
        s = s.query("match_phrase_prefix", phrase=q)
        s = s.sort("-count")
        s = s.extra(size=10)
        response = s.execute()
        result["meta"] = {
            "count": s.count(),
            "db_response_time_ms": response.took,
            "page": 1,
            "per_page": 10,
        }
        result["results"] = response
    else:
        result["meta"] = {
            "count": 0,
            "db_response_time_ms": 0,
            "page": 1,
            "per_page": 10,
        }
        result["results"] = []
    suggest_schema = SuggestMessageSchema()
    return suggest_schema.dump(result)
