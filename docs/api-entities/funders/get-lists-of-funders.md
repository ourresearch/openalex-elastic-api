# Get lists of funders

You can get lists of funders:

* Get _all_ funders in OpenAlex\
  [https://api.openalex.org/funders](https://api.openalex.org/funders)

Which returns a response like this:

```json
{
    "meta": {
        "count": 32437,
        "db_response_time_ms": 26,
        "page": 1,
        "per_page": 25
    },
    "results": [
        {
            "id": "https://openalex.org/F4320321001",
            "display_name": "National Natural Science Foundation of China",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/F4320306076",
            "display_name": "National Science Foundation",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort funders

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through funders with the `per-page` and `page` parameters:

* Get the second page of funders results, with 50 results returned per page\
  [https://api.openalex.org/funders?per-page=50\&page=2](https://api.openalex.org/funders?per-page=50\&page=2)

You also can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort funders by display name, descending\
  [https://api.openalex.org/funders?sort=display\_name:desc](https://api.openalex.org/funders?sort=display\_name:desc)

Continue on to learn how you can [filter](filter-funders.md) and [search](search-funders.md) lists of funders.

## Sample funders

You can use `sample` to get a random batch of funders. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 10 random funders\
  [https://api.openalex.org/funders?sample=10](https://api.openalex.org/funders?sample=10)

## Select fields

You can use `select` to limit the fields that are returned in a list of funders. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id`, `display_name`, and `alternate_titles` within funders results\
  [https://api.openalex.org/funders?select=id,display\_name,alternate\_titles](https://api.openalex.org/funders?select=id,display\_name,alternate\_titles)

