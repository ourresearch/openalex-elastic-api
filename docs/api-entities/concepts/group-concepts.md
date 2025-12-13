# Group concepts

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

You can group concepts with the `group_by` parameter:

* Get counts of concepts by [`level`](../concepts/concept-object.md#level):\
  [https://api.openalex.org/concepts?group\_by=level](https://api.openalex.org/concepts?group\_by=level)

Or you can group using one the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the number of results returned, and how to sort results.
{% endhint %}

### `/concepts` group\_by \_\_ attributes

* [`ancestors.id`](../concepts/concept-object.md#ancestors)
* [`cited_by_count`](../concepts/concept-object.md#cited\_by\_count)
* [`has_wikidata`](../concepts/filter-concepts.md#has\_wikidata)
* [`level`](../concepts/concept-object.md#level)
* [`summary_stats.2yr_mean_citedness`](../concepts/concept-object.md#summary\_stats)
* [`summary_stats.h_index`](../concepts/concept-object.md#summary\_stats)
* [`summary_stats.i10_index`](../concepts/concept-object.md#summary\_stats)
* [`works_count`](../concepts/concept-object.md#works\_count)
