from elasticsearch_dsl import Search
from flask import Blueprint, jsonify

from settings import (AUTHORS_INDEX, CONCEPTS_INDEX, FUNDERS_INDEX,
                      INSTITUTIONS_INDEX, PUBLISHERS_INDEX, SOURCES_INDEX,
                      WORKS_INDEX, TOPICS_INDEX, SUBFIELDS_INDEX,
                      FIELDS_INDEX, DOMAINS_INDEX, SDGS_INDEX,
                      COUNTRIES_INDEX, CONTINENTS_INDEX)

blueprint = Blueprint("counts", __name__)


@blueprint.route("/counts")
def counts():
    entities_to_indeces = {
        "authors": AUTHORS_INDEX,
        "institutions": INSTITUTIONS_INDEX,
        "sources": SOURCES_INDEX,
        "publishers": PUBLISHERS_INDEX,
        "funders": FUNDERS_INDEX,
        "works": WORKS_INDEX,
        "topics": TOPICS_INDEX,
        "subfields": SUBFIELDS_INDEX,
        "fields": FIELDS_INDEX,
        "domains": DOMAINS_INDEX,
        "sustainable_development_goals": SDGS_INDEX,
        "countries": COUNTRIES_INDEX,
        "continents": CONTINENTS_INDEX,
    }
    results = {}
    for name, index in entities_to_indeces.items():
        s = Search(index=index)
        results[name] = s.count()
    return jsonify(results)
