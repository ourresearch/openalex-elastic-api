# Get lists of sources

You can get lists of sources:

* Get _all_ sources in OpenAlex\
  [https://api.openalex.org/sources](https://api.openalex.org/sources)

Which returns a response like this:

```json
{
    "meta": {
        "count": 226727,
        "db_response_time_ms": 32,
        "page": 1,
        "per_page": 25
    },
    "results": [
        {
            "id": "https://openalex.org/S2764455111",
            "issn_l": null,
            "issn": null,
            "display_name": "PubMed Central",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/S4306400806",
            "issn_l": null,
            "issn": null,
            "display_name": "PubMed Central - Europe PMC",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort sources

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through sources with the `per-page` and `page` parameters:

* Get the second page of sources results, with 50 results returned per page\
  [https://api.openalex.org/sources?per-page=50\&page=2](https://api.openalex.org/sources?per-page=50\&page=2)

You also can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort sources by cited by count, descending\
  https://api.openalex.org/sources?sort=cited\_by\_count:desc

Continue on to learn how you can [filter](filter-sources.md) and [search](search-sources.md) lists of sources.

## Sample sources

You can use `sample` to get a random batch of sources. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 10 random sources\
  [https://api.openalex.org/sources?sample=10](https://api.openalex.org/sources?sample=10)

## Select fields

You can use `select` to limit the fields that are returned in a list of sources. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id`, `display_name` and `issn` within sources results\
  [https://api.openalex.org/sources?select=id,display\_name,issn](https://api.openalex.org/sources?select=id,display\_name,issn)
