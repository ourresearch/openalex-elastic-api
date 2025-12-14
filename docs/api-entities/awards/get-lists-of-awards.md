# Get lists of awards

You can get lists of awards:

* Get all awards in OpenAlex:\
  [`https://api.openalex.org/awards`](https://api.openalex.org/awards)

Which returns a response like this:

```json
{
    meta: {
        count: 12345678,
        db_response_time_ms: 50,
        page: 1,
        per_page: 25,
        groups_count: null
    },
    results: [
        // list of Award objects
    ]
}
```

## Page and sort awards

By default we return 25 results per page. You can change this default and [page](../../how-to-use-the-api/get-lists-of-entities/paging.md) through awards with the `per_page` and `page` parameters:

* Get the second page of awards results, with 50 results per page:\
  [`https://api.openalex.org/awards?per_page=50&page=2`](https://api.openalex.org/awards?per_page=50&page=2)

You can [sort results](../../how-to-use-the-api/get-lists-of-entities/sort-entity-lists.md) with the `sort` parameter:

* Sort awards by funded outputs count (highest first):\
  [`https://api.openalex.org/awards?sort=funded_outputs_count:desc`](https://api.openalex.org/awards?sort=funded_outputs_count:desc)

## Sample awards

You can use `sample` to get a random sample of awards. Read more about sampling and how to add a `seed` [here](../../how-to-use-the-api/get-lists-of-entities/sample-entity-lists.md).

* Get a random sample of 10 awards:\
  [`https://api.openalex.org/awards?sample=10`](https://api.openalex.org/awards?sample=10)

## Select fields

You can use `select` to limit the fields that are returned in a list of awards. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` within awards results:\
  [`https://api.openalex.org/awards?select=id,display_name`](https://api.openalex.org/awards?select=id,display_name)
