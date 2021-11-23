import random

import names
from locust import HttpUser, between, task
from utils import get_words

WORDS = get_words()
YEARS = range(1800, 2022)
GREATER_LESS_THAN = ["<", ">", ""]
PUBLISHERS = ["elsevier", "springer nature", "wiley", "oxford university press"]


class User(HttpUser):
    wait_time = between(1, 5)

    @task
    def random_query(self):
        year_query = (
            f"year={random.choice(GREATER_LESS_THAN)}{str(random.choice(YEARS))}"
        )
        group_by = random.choice(
            [f"group_by=issn", "group_by=year", "group_by=author_id"]
        )

        title = f"{random.choice(WORDS).decode('utf-8')}"
        title_query = f"title={str(title)}"

        name = random.choice([names.get_full_name(), names.get_last_name()])
        name_query = f"author_name={name}"

        publisher = random.choice(PUBLISHERS)
        publisher_query = f"publisher={publisher}"

        options = range(1, 6)
        query_options = [year_query, group_by, title_query, name_query, publisher_query]
        queries = random.sample(query_options, random.choice(options))

        queries_combined = "&".join(queries)
        self.client.get(f"/?{queries_combined}")

    # @task(1)
    # def search_by_title(self):
    #     title = f"{random.choice(WORDS).decode('utf-8')}"
    #     self.client.get(f"/?title={str(title)}")
    #
    # @task(1)
    # def search_by_author(self):
    #     name = random.choice([names.get_full_name(), names.get_last_name()])
    #     self.client.get(f"/?author_name={name}")
    #
    # @task(1)
    # def filter_by_publisher_group_by_year(self):
    #     publisher = random.choice(PUBLISHERS)
    #     self.client.get(f"/?publisher={publisher}&group_by=year")
    #
    # @task(1)
    # def filter_by_year_group_by_issn(self):
    #     year = random.choice(YEARS)
    #     self.client.get(f"/?year={year}&group_by=issn")
    #
    # @task(1)
    # def filter_by_year_group_by_author_id(self):
    #     year = random.choice(YEARS)
    #     self.client.get(f"/?year={year}&group_by=author_id")
    #
    # @task(1)
    # def filter_by_publisher_group_by_author_id(self):
    #     publisher = random.choice(PUBLISHERS)
    #     self.client.get(f"/?publisher={publisher}&group_by=author_id")
