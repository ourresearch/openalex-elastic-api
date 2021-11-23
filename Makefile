format:
	black .
	isort .

load-test:
	locust \
    --locustfile loadtest/locustfile.py \
    --host https://openalex-test-api.herokuapp.com

