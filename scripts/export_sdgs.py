import csv
import requests


UV_ID = "I212119943"


def build_csv():
    cursor = "*"
    per_page = 50
    count = 0
    with open("sdgs.csv", "a", newline="") as f:
        writer = csv.writer(f)
        headers = ["work_id", "doi", "title", "year", "source", "type", "concepts"] + [
            f"sdg_{i}_score" for i in range(1, 18)
        ]
        writer.writerow(headers)
    while cursor:
        print(
            f"https://api.openalex.org/works?filter=authorships.institutions.id:{UV_ID}&per-page={per_page}&cursor={cursor}&mailto=team@ourresearch.org"
        )
        r = requests.get(
            f"https://api.openalex.org/works?filter=authorships.institutions.id:{UV_ID}&per-page={per_page}&cursor={cursor}&mailto=team@ourresearch.org"
        )
        results = r.json()["results"]
        process_results(results)
        cursor = r.json()["meta"]["next_cursor"]
        count += len(results)
        print(f"{count} results processed out of {r.json()['meta']['count']}")


def process_results(results):
    with open("sdgs.csv", "a", newline="") as f:
        writer = csv.writer(f)
        for result in results:
            sdg_scores = {f"sdg_{i}_score": "" for i in range(1, 18)}

            for sdg in result.get("sustainable_development_goals", []):
                sdg_id = int(sdg["id"].replace("https://metadata.un.org/sdg/", ""))
                sdg_scores[f"sdg_{sdg_id}_score"] = sdg["score"]

            full_source = get_source(result)
            concepts = get_concepts(result)

            row = [
                result["id"],
                result["doi"],
                result["title"],
                result["publication_year"],
                full_source,
                result["type"],
                concepts,
            ] + [sdg_scores[f"sdg_{i}_score"] for i in range(1, 18)]

            writer.writerow(row)


def get_source(result):
    source_name = "Unknown Source"
    source_issn = "No ISSN"

    try:
        if (
            "primary_location" in result
            and result["primary_location"]
            and "source" in result["primary_location"]
        ):
            source_name = result["primary_location"]["source"].get(
                "display_name", "Unknown Source"
            )
            source_issn = result["primary_location"]["source"].get("issn_l", "No ISSN")

        full_source = (
            f"{source_name} ({source_issn})"
            if source_name != "Unknown Source" or source_issn != "No ISSN"
            else ""
        )
    except AttributeError:
        full_source = ""
    return full_source


def get_concepts(result):
    result["concepts"] = sorted(
        result.get("concepts", []), key=lambda x: x["score"], reverse=True
    )
    return ", ".join(
        [
            f"{concept['display_name']} ({concept['score']})"
            for concept in result.get("concepts", [])
        ]
    )


if __name__ == "__main__":
    build_csv()
