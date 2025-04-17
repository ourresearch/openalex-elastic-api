import os
from datetime import datetime, timezone
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import uuid
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy

# --- Dedicated SQLAlchemy Setup for Logging ---
USERS_DB_URL = os.getenv('USERS_DB_URL')
if not USERS_DB_URL:
    raise ValueError("Missing USERS_DB_URL environment variable")

users_db_url = USERS_DB_URL.replace('postgres://', 'postgresql://')

log_app = Flask(__name__)
log_app.config['SQLALCHEMY_DATABASE_URI'] = users_db_url
log_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
log_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'poolclass': sqlalchemy.pool.NullPool}

class NullPoolSQLAlchemy(SQLAlchemy):
    def apply_driver_hacks(self, app, info, options):
        options['poolclass'] = sqlalchemy.pool.NullPool
        return super(NullPoolSQLAlchemy, self).apply_driver_hacks(app, info, options)

log_db = NullPoolSQLAlchemy(log_app)


class SearchLog(log_db.Model):
    __tablename__ = 'user_search_log'

    id = log_db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    search_id = log_db.Column(log_db.String(50), nullable=True, index=True)
    user_id = log_db.Column(log_db.Text, nullable=False, index=True)
    created_at = log_db.Column(log_db.DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False, index=True)
    duration = log_db.Column(log_db.Float, nullable=True)
    results_count = log_db.Column(log_db.Integer, nullable=True)
    was_cached = log_db.Column(log_db.Boolean, nullable=True)
    sql = log_db.Column(log_db.Text, nullable=True)
    error_message = log_db.Column(log_db.Text, nullable=True)
    status = log_db.Column(log_db.String(20), nullable=True)

    def __init__(self, user_id=None, search_id=None, **kwargs):
        if user_id is None:
            raise ValueError("User ID cannot be empty.")
        if search_id is None:
            raise ValueError("Search ID cannot be empty.")

        self.search_id = search_id
        self.user_id = user_id
        self.status = "INIT"
        super().__init__(**kwargs)

    @classmethod
    def create(cls, search_id=None, user_id=None):
        if user_id is None:
            raise ValueError("User ID cannot be empty when creating a log.")
        if search_id is None:
            raise ValueError("Search ID cannot be empty when creating a log.")

        log = cls(
            search_id=search_id,
            user_id=user_id,
            status="RUNNING"
        )
        with log_app.app_context():
          try:
              #print(f"Adding log entry for search {search_id} and user {user_id}", flush=True)
              log_db.session.add(log)
              log_db.session.commit()
              return log
          except Exception as e:
              log_db.session.rollback()
              print(f"Error creating log entry: {e}")
              return None
          finally:
              log_db.session.close()

    def to_dict(self):
        return {
            'search_id': self.search_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'duration': self.duration,
            'results_count': self.results_count,
            'sql': self.sql,
            'error_message': self.error_message
        }


def update_search_logs(search_id, response):
    """
    If the response indicates that the search is complete,
    update all RUNNING logs for the given search ID for all users.
    """
    #print(f"Updating log entries for search {search_id}", flush=True)
    if response.get("is_completed"):
        was_cached = False # TODO handle this logic
        error_message = response.get("backend_error")
        status = "COMPLETE" if not error_message else "ERROR"

        try:
            running_logs = SearchLog.query.filter_by(
                search_id=search_id, status="RUNNING"
            ).all()

            for log in running_logs:
                log.duration = 0 if was_cached else response.get("timestamps", {}).get("duration")
                log.sql = response.get("redshift_sql")
                log.error_message = error_message
                log.results_count = None if error_message else response.get("meta", {}).get("count")
                log.was_cached = was_cached
                log.status = status

            log_db.session.commit()

        except Exception as e:
            log_db.session.rollback()
            print(f"Error updating log entries for search {search_id}: {e}")