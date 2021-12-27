format:
	black .
	isort .

test:
	pytest

load-test:
	locust \
    --locustfile loadtest/locustfile.py \
    --host https://elastic.api.openalex.org

