from flask import Blueprint, jsonify, request

from core.utils import get_entity_counts

blueprint = Blueprint("counts", __name__)


@blueprint.route("/counts")
def counts():
    results = get_entity_counts(request)
    return jsonify(results)
