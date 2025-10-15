from flask import Blueprint, jsonify, request

from core.utils import get_entity_counts

blueprint = Blueprint("counts", __name__)


@blueprint.route("/counts")
def counts():
    # Check data_version parameter to determine connection
    data_version = request.args.get('data_version') or request.args.get('data-version', '1')
    connection = 'walden' if data_version == '2' else 'default'

    results = get_entity_counts(connection=connection)
    return jsonify(results)
