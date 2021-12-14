format:
	black .
	isort .

load-test:
	locust \
    --locustfile loadtest/locustfile.py \
    --host https://elastic.api.openalex.org

