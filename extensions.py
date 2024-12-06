from flask_caching import Cache
from flask_compress import Compress
from flask_sqlalchemy import SQLAlchemy

cache = Cache()
compress = Compress()
db = SQLAlchemy()
