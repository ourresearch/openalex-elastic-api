# Get lists of entities

It's easy to get a list of entity objects from from the API:`/<entity_name>`. Here's an example:

* Get a list of _all_ the topics in OpenAlex:\
  [`https://api.openalex.org/topics`](https://api.openalex.org/topics)

This query returns a `meta` object with details about the query, a `results` list of [`Topic`](../../api-entities/topics/topic-object.md) objects, and an empty [`group_by`](../get-groups-of-entities.md) list:

```json
meta: {
    count: 4516,
    db_response_time_ms: 81,
    page: 1,
    per_page: 25
    },
results: [
    // long list of Topic entities
 ],
group_by: [] // empty
```

Listing entities is a lot more useful when you add parameters to [page](paging.md), [filter](filter-entity-lists.md), [search](search-entities.md), and [sort](sort-entity-lists.md) them. Keep reading to learn how to do that.
