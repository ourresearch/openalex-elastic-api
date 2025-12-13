# Filter publishers

You can filter publishers with the `filter` parameter:

* Get publishers that are hierarchy level 0\
  [`https://api.openalex.org/publishers?filter=hierarchy\_level:0`](https://api.openalex.org/publishers?filter=hierarchy\_level:0)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query
{% endhint %}

### `/publishers` attribute filters

You can filter using these attributes of the `Publisher` entity object (click each one to view their documentation on the [`Publisher`](publisher-object.md) object page):

* [`cited_by_count`](publisher-object.md#cited\_by\_count)
* [`country_codes`](publisher-object.md#country\_codes)
* [`hierarchy_level`](publisher-object.md#hierarchy\_level)
* [`ids.openalex`](publisher-object.md#ids) (alias: `openalex`)
* [`ids.ror`](publisher-object.md#ids) (alias: `ror`)
* [`ids.wikidata`](publisher-object.md#ids) (alias: `wikidata`)
* [`lineage`](publisher-object.md#lineage) — Use this with a publisher ID to find that publisher and all of its children
* [`parent_publisher`](publisher-object.md#parent\_publisher)
* [`summary_stats.2yr_mean_citedness`](publisher-object.md#summary_stats) (accepts float, null, !null, can use range queries such as < >)
* [`summary_stats.h_index`](publisher-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`summary_stats.i10_index`](publisher-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`works_count`](publisher-object.md#works\_count)

### `/publishers` convenience filters

These filters aren't attributes of the [`Publisher`](publisher-object.md) object, but they're included to address some common use cases:

#### `continent`

Value: a String with a valid [continent filter](../geo/continents.md#filter-by-continent)

Returns: publishers that are located in the chosen continent.

* Get publishers that are located in South America\
  [https://api.openalex.org/publishers?filter=continent:south\_america](https://api.openalex.org/publishers?filter=continent:south\_america)

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](./search-publishers.md#search-publishers) for Publishers.

#### `display_name.search`

Value: a search string

Returns: publishers with a [`display_name`](publisher-object.md#display\_name) containing the given string; see the [search page](search-publishers.md#search-a-specific-field) for details.

* Get publishers with names containing "elsevier":\
  [`https://api.openalex.org/publishers?filter=display_name.search:elsevier`](https://api.openalex.org/publishers?filter=display\_name.search:elsevier)``

{% hint style="info" %}
In most cases, you should use the [`search` parameter](search-publishers.md) instead of this filter because it uses a better search algorithm.
{% endhint %}
