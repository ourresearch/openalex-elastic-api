"""Settings module for test app."""
ENV = "development"
TESTING = True
SECRET_KEY = "not-so-secret-in-tests"
ES_URL = "localhost:9200"
JSON_SORT_KEYS = False
CACHE_TYPE = "NullCache"
