# Get lists of topics

You can get lists of topics:

* Get _all_ topics in OpenAlex\
  [`https://api.openalex.org/topics`](https://api.openalex.org/topics)

Which returns a response like this:

```json
{
    "meta": {
        "count": 4516,
        "db_response_time_ms": 10,
        "page": 1,
        "per_page": 25,
        "groups_count": null
    },
    "results": [
        {
            "id": "https://openalex.org/T11475",
            "display_name": "Territorial Governance and Environmental Participation",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/T13445",
            "display_name": "American Political Thought and History",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort topics

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through topics with the `per-page` and `page` parameters:

* Get the second page of topics results, with 50 results returned per page\
  [`https://api.openalex.org/topics?per-page=50\&page=2`](https://api.openalex.org/topics?per-page=50\&page=2)

You also can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort topics by cited by count, descending\
  [`https://api.openalex.org/topics?sort=cited\_by\_count:desc`](https://api.openalex.org/topics?sort=cited\_by\_count:desc)

Continue on to learn how you can [filter](../topics/filter-topics.md) and [search](../topics/search-topics.md) lists of topics.

## Sample topics

You can use `sample` to get a random batch of topics. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 10 random topics\
  [`https://api.openalex.org/topics?sample=10`](https://api.openalex.org/topics?sample=10)

## Select fields

You can use `select` to limit the fields that are returned in a list of topics. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id`, `display_name`, and `description` within topics results\
  [`https://api.openalex.org/topics?select=id,display\_name,description`](https://api.openalex.org/topics?select=id,display\_name,description)
