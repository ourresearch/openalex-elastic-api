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
                "ids.orcid",

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
                "description",
                "display_name",
                "doi",
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
                "authorships.author.id",
                "authorships.institutions.id",
                "cited_by_count",
                "display_name",
                "doi",
                "keywords.id",
                "primary_topic.domain.id",
                "primary_topic.id",
                "primary_topic.field.id",
                "primary_topic.subfield.id",
                "publication_year",
                "title",
                "type",
            ]
        }
        return False # Turn off elastic routing
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
            elif "." in column:
                columns.append(column.split(".")[0])
            else:
                columns.append(column)
        if "id" not in columns:
            columns.append("id")
        columns = list(set(columns))
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
        def convert_topic_field(result, entity_key, entity_name):
            entity = result.get("primary_topic", {}).get(entity_key, {}) if result.get("primary_topic") else {}
            entity_id = entity.get("id")
            short_id = self.get_id_from_openalex_id(entity_id)
            if short_id:
                result[f"primary_topic.{entity_key}.id"] = {
                    "id": f"{entity_name}/{short_id}",
                    "display_name": entity.get("display_name"),
                }

        for result in results:
            for key, value in list(result.items()):
                if key == "id":
                    result[key] = self.convert_id_to_short_format(value)
                elif key == "authorships":
                    result["authorships.author.id"] = [
                        {
                            "id": f"authors/{self.get_id_from_openalex_id(author.get('author').get('id'))}",
                            "display_name": author.get("author").get("display_name"),
                        }
                        for author in value
                    ]
                    # ensure unique institutions
                    seen_institutions = set()
                    unique_institutions = []
                    for author in value:
                        for institution in author.get("institutions", []):
                            institution_id = self.get_id_from_openalex_id(institution.get("id"))
                            if institution_id not in seen_institutions:
                                unique_institutions.append({
                                    "id": f"institutions/{institution_id}",
                                    "display_name": institution.get("display_name"),
                                })
                                seen_institutions.add(institution_id)

                    result["authorships.institutions.id"] = unique_institutions
                    del result[key]
                elif key == "keywords":
                    result["keywords.id"] = [
                        {
                            "id": f"keywords/{self.get_id_from_openalex_id(keyword.get('id'))}",
                            "display_name": keyword.get("display_name"),
                        }
                        for keyword in value
                    ]
                    del result[key]
                elif key == "primary_topic":
                    topic_id = result.get("primary_topic").get("id") if result.get("primary_topic") else None
                    short_id = self.get_id_from_openalex_id(topic_id)
                    if short_id:
                        result["primary_topic.id"] = {
                            "id": f"topics/{short_id}",
                            "display_name": result["primary_topic"].get("display_name"),
                        }
                    # Handle nested fields
                    convert_topic_field(result, "domain", "domains")
                    convert_topic_field(result, "field", "fields")
                    convert_topic_field(result, "subfield", "subfields")
                elif key == "type" and self.entity == "works":
                    result[key] = {
                        "id": f"types/{value}",
                        "display_name": value,
                    }
                elif key == "works_count":
                    result["count(works)"] = value
                    del result[key]
                else:
                    result[key] = value
        return results

    def convert_id_to_short_format(self, id):
        short_id = id.split("/")[-1]
        return f"{self.entity}/{short_id}"

    @staticmethod
    def get_id_from_openalex_id(openalex_id):
        return openalex_id.split("/")[-1] if openalex_id else None

    def get_entity_config(self):
        entity_for_config = "works" if self.entity == "summary" else self.entity
        return all_entities_config.get(entity_for_config).get("columns")
