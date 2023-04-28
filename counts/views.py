from elasticsearch_dsl import Search
from flask import Blueprint, jsonify

from settings import (AUTHORS_INDEX, CONCEPTS_INDEX, INSTITUTIONS_INDEX,
                      SOURCES_INDEX, WORKS_INDEX, PUBLISHERS_INDEX, FUNDERS_INDEX)

blueprint = Blueprint("counts", __name__)


@blueprint.route("/counts")
def counts():
    entities_to_indeces = {
        "authors": AUTHORS_INDEX,
        "concepts": CONCEPTS_INDEX,
        "institutions": INSTITUTIONS_INDEX,
        "sources": SOURCES_INDEX,
        "publishers": PUBLISHERS_INDEX,
        "funders": FUNDERS_INDEX,
        "works": WORKS_INDEX,
    }
    results = {}
    for name, index in entities_to_indeces.items():
        s = Search(index=index)
        results[name] = s.count()
    return jsonify(results)
