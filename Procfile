web: gunicorn "app:create_app()" -w $WEB_WORKERS_PER_DYNO --log-level warning
process_searches: python -m process_searches
process_test_job: python -m oql.process_bulk_tests