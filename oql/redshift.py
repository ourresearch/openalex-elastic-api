import os
import re
from urllib.parse import urlparse

import psycopg2
import requests


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REDSHIFT_URL = os.getenv("REDSHIFT_SERVERLESS_URL")
redshift = urlparse(REDSHIFT_URL)


REDSHIFT_SCHEMA = {
    "affiliation": [
        ("paper_id", "BIGINT"),
        ("author_id", "BIGINT"),
        ("affiliation_id", "BIGINT"),
        ("author_sequence_number", "INTEGER"),
        ("original_author", "VARCHAR(65535)"),
        ("original_orcid", "VARCHAR(500)")
    ],
    "author": [
        ("author_id", "BIGINT"),
        ("display_name", "VARCHAR(65535)"),
        ("merge_into_id", "BIGINT")
    ],
    "citation": [
        ("paper_id", "BIGINT"),
        ("paper_reference_id", "BIGINT")
    ],
    "subfield": [
        ("subfield_id", "INTEGER"),
        ("display_name", "VARCHAR(65535)"),
        ("description", "VARCHAR(65535)"),
    ],
    "topic": [
        ("topic_id", "INTEGER"),
        ("display_name", "VARCHAR(65535)"),
        ("summary", "VARCHAR(65535)"),
        ("keywords", "VARCHAR(65535)"),
        ("subfield_id", "INTEGER"),
        ("field_id", "INTEGER"),
        ("domain_id", "INTEGER"),
        ("wikipedia_url", "VARCHAR(65535)"),
    ],
    "work": [
        ("paper_id", "BIGINT"),
        ("original_title", "VARCHAR(65535)"),
        ("doi_lower", "VARCHAR(500)"),
        ("journal_id", "BIGINT"),
        ("merge_into_id", "BIGINT"),
        ("publication_date", "VARCHAR(500)"),
        ("doc_type", "VARCHAR(500)"),
        ("genre", "VARCHAR(500)"),
        ("arxiv_id", "VARCHAR(500)"),
        ("is_paratext", "BOOLEAN"),
        ("best_url", "VARCHAR(65535)"),
        ("best_free_url", "VARCHAR(65535)"),
        ("oa_status", "VARCHAR(500)"),
        ("type", "VARCHAR(500)"),
        ("type_crossref", "VARCHAR(500)"),
        ("year", "INTEGER"),
        ("created_date", "VARCHAR(500)")
    ],
    "work_concept": [
        ("paper_id", "BIGINT"),
        ("field_of_study", "BIGINT")
    ],
    "work_topic": [
        ("paper_id", "BIGINT"),
        ("topic_id", "INTEGER"),
        ("score", "FLOAT")
    ],

}


def get_redshift_connection():
    conn = psycopg2.connect(
        dbname=redshift.path[1:],
        user=redshift.username,
        password=redshift.password,
        host=redshift.hostname,
        port=redshift.port,
    )
    return conn


def execute_redshift_query(query):
    validate_redshift_query(query)
    conn = get_redshift_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()


def build_redshift_query(oql_query):
    # call openai chatgpt to generate a redshift query
    clean_query = clean_oql_query(oql_query)
    context = (
        f"given a redshift schema with tables in the following schema: {REDSHIFT_SCHEMA}"
        f" convert the following query to a redshift query: {clean_query} and only return the redshift query that is"
        f" needed to get results, formatted as a single string with no other context. Order by count desc if count"
        f" is one of the columns. An institution and affiliation are the same thing."
    )
    if "subfield" in oql_query:
        print(f"adding more context for subfield query: {oql_query}")
        subfield_context = ("To get subfields, join work_topic.paper_id to work.paper_id, then use the topic_id to get the subfield from the topic table. "
                            "When grouping by a subfield, return in order: subfield_id, display_name, count, and share.")
        context = f"{context} {subfield_context}"
    response = call_openai_chatgpt(context)
    redshift_query = format_chatgpt_response(response)
    return redshift_query


def clean_oql_query(oql_query):
    # detect integer in I1234 and replace with the integer
    print(oql_query)
    oql_query = re.sub(r"\bI(\d+)\b", r"\1", oql_query)
    # remove the word "using" and replace with "from"
    oql_query = re.sub(r"\busing\b", "from", oql_query)
    return oql_query


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


def validate_redshift_query(query):
    print(f"Validating Redshift query: {query}")
    if "select" not in query.lower():
        raise ValueError("Redshift query must contain a SELECT statement.")
    if "delete" in query.lower():
        raise ValueError("Redshift query cannot contain a DELETE statement.")
    if "drop" in query.lower():
        raise ValueError("Redshift query cannot contain a DROP statement.")


if __name__ == "__main__":
    oql_query = "using works where institution is i33213144 and type is article and publication_year is >= 2004 get subfields return count, share_of(count)"
    query = build_redshift_query(oql_query)
    print(query)
