from collections import OrderedDict

from elasticsearch_dsl import Search
from flask import Blueprint, request

from complete.schemas import MessageSchema

blueprint = Blueprint("complete", __name__)


@blueprint.route("/autocomplete")
def autocomplete():
    q = request.args.get("q")
    s = Search(
        index="authors-v3,concepts-v1,institutions-v1,venues-v2,works-v5-*,-*invalid-data"
    )
    s = s.query("match_phrase_prefix", display_name=q)
    s = s.sort("-cited_by_count")
    response = s.execute()

    result = OrderedDict()
    result["meta"] = {
        "count": s.count(),
        "db_response_time_ms": response.took,
        "page": 1,
        "per_page": 10,
    }
    result["results"] = response
    message_schema = MessageSchema()
    return message_schema.dump(result)
