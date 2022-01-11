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

test-dump-elasticsearch:
	multielasticdump \
	  --direction dump \
	  --input=http://localhost:9200 \
	  --output=/tmp/es_backup

test-ingest-elasticsearch:
	multielasticdump \
	  --direction=load \
	  --input=/tmp/es_backup \
	  --output=http://localhost:9200