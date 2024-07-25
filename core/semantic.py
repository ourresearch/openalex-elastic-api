import os
import requests

from elasticsearch import Elasticsearch


def semantic_search(text):
    embedding = call_embeddings_api(text)
    work_ids_with_scores, response_time = knn_query(embedding)
    response = format_response(work_ids_with_scores, response_time)
    return response


def call_embeddings_api(text):
    api_key = os.getenv("OPENAI_API_KEY")

    url = "https://api.openai.com/v1/embeddings"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    data = {"input": text, "model": "text-embedding-3-large", "dimensions": 256}

    response = requests.post(url, headers=headers, json=data)
    embedding = response.json()["data"][0]["embedding"]
    return embedding


def knn_query(embedding, k=10):
    es = Elasticsearch([os.getenv("ELASTIC_SEMANTIC_URL")])
    query = {
        "knn": {
            "field": "embedding",
            "query_vector": embedding,
            "k": k,
            "num_candidates": 100,
        },
        "_source": ["work_id"],  # Specify the source fields to be returned
    }
    response = es.search(index="work-embeddings-v2", body=query)
    work_ids_with_scores = [
        (hit["_source"]["work_id"], hit["_score"]) for hit in response["hits"]["hits"]
    ]
    response_time = response["took"]
    return work_ids_with_scores, response_time


def total_record_count():
    es = Elasticsearch([os.getenv("ELASTIC_SEMANTIC_URL")])
    response = es.count(index="work-embeddings-v2", body={"query": {"match_all": {}}})
    return response["count"]


def format_response(work_ids_with_scores, response_time):
    joined_work_ids = "|".join(
        f"W{str(work_id)}" for work_id, _ in work_ids_with_scores
    )
    r = requests.get(
        "https://api.openalex.org/works?filter=ids.openalex:{0}".format(joined_work_ids)
    )
    response_json = r.json()

    # Attach scores to the response
    for work in response_json["results"]:
        work_id_int = int(work["id"].replace("https://openalex.org/W", ""))
        score = next(
            score for work_id, score in work_ids_with_scores if work_id == work_id_int
        )
        work["score"] = score

    response_json["meta"] = {
        "total_embeddings": total_record_count(),
        "db_response_time_ms": response_time,
    }
    # limit fields in results to id, display_name, abstract_inverted_index
    response_json["results"] = [
        {
            k: v
            for k, v in work.items()
            if k in ["id", "display_name", "abstract_inverted_index", "score"]
        }
        for work in response_json["results"]
    ]
    # ensure results sorted by score
    response_json["results"] = sorted(
        response_json["results"], key=lambda x: x["score"], reverse=True
    )
    return response_json
