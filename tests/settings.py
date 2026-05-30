"""Settings module for test app."""
ENV = "development"
TESTING = True
SECRET_KEY = "not-so-secret-in-tests"
ES_URL_WALDEN = "localhost:9200"
JSON_SORT_KEYS = False
CACHE_TYPE = "NullCache"
# In-memory SQLite for test runs — Flask-SQLAlchemy refuses to init without a
# URI. None of the existing tests touch SQL, so a throwaway db is fine.
SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
SQLALCHEMY_TRACK_MODIFICATIONS = False
