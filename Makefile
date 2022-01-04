format:
	black .
	isort .

test:
	pytest

load-test:
	locust \
    --locustfile loadtest/locustfile.py \
    --host https://elastic.api.openalex.org

test_up:
	docker-compose -f tests/docker-compose.yml up -d

test_stop:
	docker-compose -f tests/docker-compose.yml stop

kibana:
	python -m webbrowser "http://localhost:5601/app/home#/"