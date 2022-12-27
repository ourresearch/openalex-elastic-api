import os

CACHE_TYPE = "RedisCache"
CACHE_DEFAULT_TIMEOUT = 300
CACHE_REDIS_URL = os.environ.get("REDISCLOUD_URL")
ENV = os.environ.get("FLASK_ENV", "production")
ES_URL = os.environ.get("ES_URL_PROD", "http://elastic:testpass@127.0.0.1:9200")
DEBUG = ENV == "development"
JSON_SORT_KEYS = False
SECRET_KEY = os.environ.get("SECRET_KEY")

# indexes
AUTHORS_INDEX = "authors-v10"
CONCEPTS_INDEX = "concepts-v8"
INSTITUTIONS_INDEX = "institutions-v4"
VENUES_INDEX = "venues-v8"
WORKS_INDEX = "works-v16-*,-*invalid-data"

DO_NOT_GROUP_BY = [
    "cited_by",
    "display_name",
    "doi",
    "ids.mag",
    "ids.pmid",
    "ids.pmcid",
    "mag",
    "pmid",
    "pmcid",
    "related_to",
    "repository",
]

EXTERNAL_ID_FIELDS = [
    "has_doi",
    "has_issn",
    "has_orcid",
    "has_pmid",
    "has_pmcid",
    "has_orcid",
    "has_ror",
    "has_wikidata",
]

BOOLEAN_TEXT_FIELDS = ["has_abstract", "has_ngrams", "has_references"]

TRANSFORMS = [
    {
        "field": "x_concepts.id",
        "index_name": "authors-transform-x-concepts-id",
        "parent_index": "authors",
    }
]

CONTINENT_PARAMS = {
    "africa": "Q15",
    "antarctica": "Q51",
    "asia": "Q48",
    "europe": "Q46",
    "north_america": "Q49",
    "oceania": "Q55643",
    "south_america": "Q18",
}


CONTINENT_NAMES = [
    {"display_name": "Africa", "id": "Q15", "param": "africa"},
    {"display_name": "Antarctica", "id": "Q51", "param": "antarctica"},
    {"display_name": "Asia", "id": "Q48", "param": "asia"},
    {"display_name": "Europe", "id": "Q46", "param": "europe"},
    {"display_name": "North America", "id": "Q49", "param": "north_america"},
    {"display_name": "Oceania", "id": "Q55643", "param": "oceania"},
    {"display_name": "South America", "id": "Q18", "param": "south_america"},
]

VERSIONS = ["null", "acceptedVersion", "submittedVersion", "publishedVersion"]
