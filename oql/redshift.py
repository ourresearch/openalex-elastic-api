import os

from sqlalchemy import desc
from extensions import db
from oql import models
import requests


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class RedshiftQueryHandler:
    def __init__(self, entity, sort_by_column, sort_by_order, filter_by, valid_columns):
        self.entity = entity
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.filter_by = filter_by
        self.valid_columns = valid_columns

    def redshift_query(self):
        entity_class = self.get_entity_class()

        results = db.session.query(entity_class)
        results = self.apply_sort(results, entity_class)
        results = self.apply_filter(results, entity_class)
        return results.limit(100).all()

    def get_entity_class(self):
        if self.entity == "countries":
            entity_class = getattr(models, "Country")
        elif self.entity == "institution-types":
            entity_class = getattr(models, "InstitutionType")
        elif self.entity == "source-types":
            entity_class = getattr(models, "SourceType")
        elif self.entity == "work-types":
            entity_class = getattr(models, "WorkType")
        else:
            entity_class = getattr(models, self.entity[:-1].capitalize())
        return entity_class

    def apply_sort(self, query, entity_class):
        if self.sort_by_column:
            if self.sort_by_column == "publication_year":
                model_column = getattr(entity_class, "year")
            else:
                model_column = getattr(entity_class, self.sort_by_column, None)

            if model_column:
                query = query.order_by(model_column) if self.sort_by_order == "asc" else query.order_by(desc(model_column))
            else:
                query = self.default_sort(query, entity_class)
        else:
            query = self.default_sort(query, entity_class)

        return query

    def default_sort(self, query, entity_class):
        default_sort_column = "cited_by_count" if self.entity == "works" else "display_name"
        return query.order_by(desc(getattr(entity_class, default_sort_column, None)))

    def apply_filter(self, query, entity_class):
        if not self.filter_by:
            return query

        filters = self.filter_by
        for key, value in filters.items():
            if key == "id":
                query = query.filter(getattr(entity_class, "paper_id") == value)
            elif key == "publication_year":
                query = query.filter(getattr(entity_class, "year") == value)
            else:
                column = getattr(entity_class, key, None)
                query = query.filter(column == value)
        return query


def call_openai_chatgpt(prompt):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key is missing. Set it as an environment variable."
        )

    url = "https://api.openai.com/v1/chat/completions"
    messages = [
        {
            "role": "system",
            "content": "You are a database administrator for a company that uses Redshift.",
        },
        {"role": "user", "content": prompt},
    ]
    data = {
        "model": "gpt-4o",
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.5,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    r = requests.post(url, json=data, headers=headers)

    if r.status_code == 200:
        return r.json()
    else:
        raise Exception(f"Error: {r.status_code} - {r.text}")


def format_chatgpt_response(response):
    content = response["choices"][0]["message"]["content"]
    clean_content = (
        content.replace("\n", " ")
        .replace("  ", " ")
        .replace("sql", "")
        .replace("`", "")
        .strip()
    )
    return clean_content
