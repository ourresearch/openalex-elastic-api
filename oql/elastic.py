import requests

from combined_config import all_entities_config


class ElasticQueryHandler:
    def __init__(
        self,
        entity,
        filter_works,
        filter_aggs,
        show_columns,
        sort_by_column,
        sort_by_order,
        valid_columns,
    ):
        self.entity = entity
        self.filter_works = filter_works
        self.filter_aggs = filter_aggs
        self.show_columns = show_columns
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.valid_columns = valid_columns
        self.entity_config = self.get_entity_config()
        self.works_config = all_entities_config.get("works").get("columns")

    def execute(self):
        r = requests.get(
            "https://api.openalex.org/works?per-page=100&sort=cited_by_count:desc"
        )
        raw_results = r.json()["results"]
        results = self.transform_ids(raw_results)
        total_count = r.json()["meta"]["count"]
        return total_count, results

    def build_url(self):
        sort_by_column = (
            self.sort_by_column
            if self.sort_by_column in self.works_config
            else "cited_by_count"
        )
        sort_by_order = (
            self.sort_by_order if self.sort_by_order in ["asc", "desc"] else "desc"
        )
        select_columns = ",".join(self.show_columns)
        url = f"https://api.openalex.org/works?select={select_columns}&per-page=100&sort={sort_by_column}:{sort_by_order}&mailto=team@ourresearch.org"
        return url

    def transform_ids(self, results):
        for result in results:
            for key, value in result.items():
                # type
                if key == "type" and self.entity == "works":
                    result[key] = {
                        "id": f"types/{value}",
                        "display_name": value,
                    }
                else:
                    result[key] = value
        return results

    def is_valid(self):
        valid_elastic_columns = {
            "works": [
                "id",
                "display_name",
                "title",
                "type",
                "doi",
                "publication_year",
                "cited_by_count",
            ]
        }
        return (
            self.entity == "works"
            and not self.filter_aggs
            and all(
                column in valid_elastic_columns.get(self.entity)
                for column in self.show_columns
            )
        )

    def get_entity_config(self):
        entity_for_config = "works" if self.entity == "summary" else self.entity
        return all_entities_config.get(entity_for_config).get("columns")
