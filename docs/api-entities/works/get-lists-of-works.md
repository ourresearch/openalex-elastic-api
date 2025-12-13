# Get lists of works

You can get lists of works:

* Get _all_ of the works in OpenAlex\
  [`https://api.openalex.org/works`](https://api.openalex.org/works)

Which returns a response like this:

```json
{
    "meta": {
        "count": 245684392,
        "db_response_time_ms": 929,
        "page": 1,
        "per_page": 25
    },
    "results": [
        {
            "id": "https://openalex.org/W1775749144",
            "doi": "https://doi.org/10.1016/s0021-9258(19)52451-6",
            "title": "PROTEIN MEASUREMENT WITH THE FOLIN PHENOL REAGENT",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/W2100837269",
            "doi": "https://doi.org/10.1038/227680a0",
            "title": "Cleavage of Structural Proteins during the Assembly of the Head of Bacteriophage T4",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Page and sort works

You can [page through](../../how-to-use-the-api/get-lists-of-entities/paging.md) works and change the default number of results returned with the `page` and `per-page` parameters:

* Get a second page of results with 50 results per page\
  [`https://api.openalex.org/works?per-page=50\&page=2`](https://api.openalex.org/works?per-page=50\&page=2)

You can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort works by publication year\
  [`https://api.openalex.org/works?sort=publication\_year`](https://api.openalex.org/works?sort=publication\_year)

Continue on to learn how you can [filter](filter-works.md) and [search](search-works.md) lists of works.

## Sample works

You can use `sample` to get a random batch of works. Read more about sampling and how to add a `seed` value [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get 20 random works\
  [`https://api.openalex.org/works?sample=20`](https://api.openalex.org/works?sample=20)

## Select fields

You can use `select` to limit the fields that are returned in a list of works. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` within works results\
  [`https://api.openalex.org/works?select=id,display\_name`](https://api.openalex.org/works?select=id,display\_name)
