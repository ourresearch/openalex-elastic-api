# Group topics

You can group topics with the `group_by` parameter:

* Get counts of topics by [`domain`](../topics/topic-object.md#domain):\
  [`https://api.openalex.org/topics?group_by=domain.id`](https://api.openalex.org/topics?group_by=domain.id)

Or you can group using one the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the number of results returned, and how to sort results.
{% endhint %}

### Topics group_by attributes

* [`cited_by_count`](./topic-object.md#cited_by_count)
* [`domain.id`](./topic-object.md#domain)
* [`field.id`](./topic-object.md#field)
* [`subfield.id`](./topic-object.md#subfield)
* [`works_count`](./topic-object.md#works_count)
