format:
	black .
	isort .

kibana:
	python -m webbrowser "http://localhost:5601/app/home#/"

load-test:
	locust \
    --locustfile loadtest/locustfile.py \
    --host https://elastic.api.openalex.org

test-up:
	docker-compose -f tests/docker-compose.yml up -d

test-stop:
	docker-compose -f tests/docker-compose.yml stop

test:
	pytest