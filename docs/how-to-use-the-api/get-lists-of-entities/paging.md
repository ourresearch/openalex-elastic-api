# Paging

{% hint style="info" %}
You can see executable examples of paging in [this user-contributed Jupyter notebook!](https://github.com/ourresearch/openalex-api-tutorials/blob/main/notebooks/getting-started/paging.ipynb)
{% endhint %}

### Basic paging

Use the `page` query parameter to control which page of results you want (eg `page=1`, `page=2`, etc). By default there are 25 results per page; you can use the `per-page` parameter to change that to any number between 1 and 200.

* Get the 2nd page of a list:\
  [`https://api.openalex.org/works?page=2`](https://api.openalex.org/works?page=2)
* Get 200 results on the second page:\
  [`https://api.openalex.org/works?page=2&per-page=200`](https://api.openalex.org/works?page=2\&per-page=200)

Basic paging only works to get the first 10,000 results of any list. If you want to see more than 10,000 results, you'll need to use [cursor paging](paging.md#cursor-paging).

### Cursor paging

Cursor paging is a bit more complicated than [basic paging](paging.md#basic-paging), but it allows you to access as many records as you like.&#x20;

To use cursor paging, you request a cursor by adding the `cursor=*` parameter-value pair to your query.

* Get a cursor in order to start cursor pagination:\
  [`https://api.openalex.org/works?filter=publication_year:2020&per-page=100&cursor=*`](https://api.openalex.org/works?filter=publication\_year:2020\&per-page=100\&cursor=\*)

The response to your query will include a `next_cursor` value in the response's `meta` object. Here's what it looks like:&#x20;

```json
{
  "meta": {
    "count": 8695857,
    "db_response_time_ms": 28,
    "page": null,
    "per_page": 100,
    "next_cursor": "IlsxNjA5MzcyODAwMDAwLCAnaHR0cHM6Ly9vcGVuYWxleC5vcmcvVzI0ODg0OTk3NjQnXSI="
  },
  "results" : [
    // the first page of results
  ]
}
```

To retrieve the next page of results, copy the `meta.next_cursor` value into the cursor field of your next request.

* Get the next page of results using a cursor value: \
  [`https://api.openalex.org/works?filter=publication_year:2020&per-page=100&cursor=IlsxNjA5MzcyODAwMDAwLCAnaHR0cHM6Ly9vcGVuYWxleC5vcmcvVzI0ODg0OTk3NjQnXSI=`](https://api.openalex.org/works?filter=publication\_year:2020\&per-page=100\&cursor=IlsxNjA5MzcyODAwMDAwLCAnaHR0cHM6Ly9vcGVuYWxleC5vcmcvVzI0ODg0OTk3NjQnXSI=)

This second page of results will have a new value for `meta.next_cursor`. You'll use this new value the same way you did the first, and it'll give you the second page of results. To get _all_ the results, keep repeating this process until `meta.next_cursor` is null and the `results` set is empty.

Besides using cursor paging to get entities, you can also use it in [`group_by` queries](../get-groups-of-entities.md).

{% hint style="danger" %}
**Don't use cursor paging to download the whole dataset.**

* It's bad for you because it will take many days to page through a long list like /works or /authors.
* It's bad for us (and other users!) because it puts a massive load on our servers.

Instead, download everything at once, using the [OpenAlex snapshot](../../download-all-data/openalex-snapshot.md). It's free, easy, fast, and you get all the results in same format you'd get from the API.
{% endhint %}
