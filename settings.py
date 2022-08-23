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
AUTHORS_INDEX = "authors-v7"
CONCEPTS_INDEX = "concepts-v6"
INSTITUTIONS_INDEX = "institutions-v4"
VENUES_INDEX = "venues-v5"
WORKS_INDEX = "works-v14-*,-*invalid-data"

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
]

EXTERNAL_ID_FIELDS = [
    "has_doi",
    "has_issn",
    "has_orcid",
    "has_ror",
    "has_wikidata",
]

TRANSFORMS = [
    {
        "field": "x_concepts.id",
        "index_name": "authors-transform-x-concepts-id",
        "parent_index": "authors",
    }
]
