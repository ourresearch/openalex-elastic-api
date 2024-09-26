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

    def is_valid(self):
        valid_elastic_columns = {
            "authors": [
                "id",
                "count(works)",
                "display_name",
                "orcid",
            ],
            "countries": [
                "id",
                "count(works)",
                "display_name",
            ],
            "domains": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "fields": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "funders": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "institution-types": [
                "id",
                "count(works)",
                "display_name",
            ],
            "institutions": [
                "id",
                "count(works)",
                "display_name",
            ],
            "keywords": [
                "id",
                "count(works)",
                "display_name",
            ],
            "languages": [
                "id",
                "count(works)",
                "display_name",
            ],
            "licenses": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "publishers": [
                "id",
                "count(works)",
                "display_name",
            ],
            "sdgs": [
                "id",
                "count(works)",
                "display_name",
            ],
            "source-types": [
                "id",
                "count(works)",
                "display_name",
            ],
            "sources": [
                "id",
                "count(works)",
                "display_name",
            ],
            "subfields": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "topics": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "work-types": [
                "id",
                "count(works)",
                "display_name",
                "description",
            ],
            "works": [
                "id",
                "cited_by_count",
                "display_name",
                "doi",
                "publication_year",
                "title",
                "type",
            ]
        }
        return (
            self.entity in valid_elastic_columns.keys()
            and not self.filter_works
            and not self.filter_aggs
            and all(
                column in valid_elastic_columns.get(self.entity)
                for column in self.show_columns
            )
        )

    def execute(self):
        url = self.build_url()
        r = requests.get(url)
        raw_results = r.json()["results"]
        results = self.transform_ids(raw_results)
        total_count = r.json()["meta"]["count"]
        return total_count, results

    def build_url(self):
        sort_by_column = self.build_sort()
        sort_by_order = (
            self.sort_by_order if self.sort_by_order in ["asc", "desc"] else "desc"
        )
        select_columns = self.build_select_columns()
        url = f"https://api.openalex.org/{self.entity}?select={select_columns}&per-page=100&sort={sort_by_column}:{sort_by_order}&mailto=team@ourresearch.org"
        return url

    def build_select_columns(self):
        columns = []
        for column in self.show_columns:
            if column == "count(works)":
                columns.append("works_count")
            else:
                columns.append(column)
        if "id" not in columns:
            columns.append("id")
        return ",".join(columns)

    def build_sort(self):
        if self.sort_by_column == "count(works)":
            sort_by_column = "works_count"
        elif self.sort_by_column:
            sort_by_column = self.sort_by_column
        elif self.entity == "works":
            sort_by_column = "cited_by_count"
        else:
            sort_by_column = "works_count"
        return sort_by_column

    def transform_ids(self, results):
        for result in results:
            for key, value in list(result.items()):
                # id
                if key == "id":
                    result[key] = self.convert_id_to_short_format(value)
                # type
                elif key == "type" and self.entity == "works":
                    result[key] = {
                        "id": f"types/{value}",
                        "display_name": value,
                    }
                # works_count -> count(works)
                elif key == "works_count":
                    result["count(works)"] = value  # Assign value to the new key
                    del result[key]  # Optionally delete the original key
                else:
                    result[key] = value
        return results

    def convert_id_to_short_format(self, id):
        short_id = id.split("/")[-1]
        return f"{self.entity}/{short_id}"

    def get_entity_config(self):
        entity_for_config = "works" if self.entity == "summary" else self.entity
        return all_entities_config.get(entity_for_config).get("columns")
