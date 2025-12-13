# Get lists of authors

You can get lists of authors:

* Get _all_ authors in OpenAlex\
  [`https://api.openalex.org/authors`](https://api.openalex.org/authors)

Which returns a response like this:

```json
{
    "meta": {
        "count": 93011659,
        "db_response_time_ms": 150,
        "page": 1,
        "per_page": 25
    },
    "results": [
        {
            "id": "https://openalex.org/A5053780153",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/A5032245741",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort authors

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through works with the `per-page` and `page` parameters:

* Get the second page of authors results, with 50 results returned per page\
  [`https://api.openalex.org/authors?per-page=50\&page=2`](https://api.openalex.org/authors?per-page=50\&page=2)

You also can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort authors by cited by count, descending\
  [`https://api.openalex.org/authors?sort=cited\_by\_count:desc`](https://api.openalex.org/authors?sort=cited\_by\_count:desc)

Continue on to learn how you can [filter](filter-authors.md) and [search](search-authors.md) lists of authors.

## Sample authors

You can use `sample` to get a random batch of authors. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 25 random authors\
  [`https://api.openalex.org/authors?sample=25`](https://api.openalex.org/authors?sample=25)

## Select fields

You can use `select` to limit the fields that are returned in a list of authors. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` and `orcid` within authors results\
  [`https://api.openalex.org/authors?select=id,display\_name,orcid`](https://api.openalex.org/authors?select=id,display\_name,orcid)
