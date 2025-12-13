# Filter concepts

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

You can filter concepts with the `filter` parameter:

* Get concepts that are at level 0 (top level)\
  [`https://api.openalex.org/concepts?filter=level:0`](https://api.openalex.org/concepts?filter=level:0)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query
{% endhint %}

### `/concepts` attribute filters

You can filter using these attributes of the [`Concept`](../concepts/concept-object.md) object (click each one to view their documentation on the `Concept` object page):

* [`ancestors.id`](../concepts/concept-object.md#ancestors)
* [`cited_by_count`](../concepts/concept-object.md#cited\_by\_count)
* [`ids.openalex`](../concepts/concept-object.md#ids) (alias: `openalex`)
* [`level`](../concepts/concept-object.md#level)
* [`summary_stats.2yr_mean_citedness`](../concepts/concept-object.md#summary\_stats) (accepts float, null, !null, can use range queries such as < >)
* [`summary_stats.h_index`](../concepts/concept-object.md#summary\_stats) (accepts integer, null, !null, can use range queries)
* [`summary_stats.i10_index`](../concepts/concept-object.md#summary\_stats) (accepts integer, null, !null, can use range queries)
* [`works_count`](../concepts/concept-object.md#works\_count)

### `/concepts` convenience filters

These filters aren't attributes of the [`Concept`](../concepts/concept-object.md) object, but they're included to address some common use cases:

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](../concepts/search-concepts.md#search-concepts) for Concepts.

#### `display_name.search`

Value: a search string

Returns: concepts with a [`display_name`](../concepts/concept-object.md#display\_name) containing the given string; see the [search page](../concepts/search-concepts.md#search-a-specific-field) for details.

* Get concepts with `display_name` containing "electrodynamics":\
  [`https://api.openalex.org/concepts?filter=display_name.search:electrodynamics`](https://api.openalex.org/concepts?filter=display\_name.search:electrodynamics)

{% hint style="info" %}
In most cases, you should use the [`search` parameter](../concepts/search-concepts.md#concepts-full-search) instead of this filter because it uses a better search algorithm.
{% endhint %}

#### `has_wikidata`

Value: a Boolean (`true` or `false`)

Returns: concepts that have or lack a [Wikidata ID](../concepts/concept-object.md#wikidata), depending on the given value. For now, all concepts in OpenAlex _do_ have Wikidata IDs.

* Get concepts without Wikidata IDs:\
  [`https://api.openalex.org/concepts?filter=has_wikidata:false`](https://api.openalex.org/concepts?filter=has\_wikidata:false)
