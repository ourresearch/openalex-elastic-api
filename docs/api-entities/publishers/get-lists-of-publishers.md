# Get lists of publishers

You can get lists of publishers:

* Get _all_ publishers in OpenAlex\
  [https://api.openalex.org/publishers](https://api.openalex.org/publishers)

Which returns a response like this:

```json
{
    "meta": {
        "count": 7207,
        "db_response_time_ms": 26,
        "page": 1,
        "per_page": 25
    },
    "results": [
        {
            "id": "https://openalex.org/P4310311775",
            "display_name": "RELX Group",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/P4310320990",
            "display_name": "Elsevier BV",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort publishers

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through publishers with the `per-page` and `page` parameters:

* Get the second page of publishers results, with 50 results returned per page\
  [https://api.openalex.org/publishers?per-page=50\&page=2](https://api.openalex.org/publishers?per-page=50\&page=2)

You also can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort publishers by display name, descending\
  [https://api.openalex.org/publishers?sort=display\_name:desc](https://api.openalex.org/publishers?sort=display\_name:desc)

Continue on to learn how you can [filter](filter-publishers.md) and [search](search-publishers.md) lists of publishers.

## Sample publishers

You can use `sample` to get a random batch of publishers. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 10 random publishers\
  [https://api.openalex.org/publishers?sample=10](https://api.openalex.org/publishers?sample=10)

## Select fields

You can use `select` to limit the fields that are returned in a list of publishers. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id`, `display_name`, and `alternate_titles` within publishers results\
  [https://api.openalex.org/publishers?select=id,display\_name,alternate\_titles](https://api.openalex.org/publishers?select=id,display\_name,alternate\_titles)
