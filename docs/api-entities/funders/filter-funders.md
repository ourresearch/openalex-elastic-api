# Filter funders

You can filter funders with the `filter` parameter:

* Get funders that are located in Canada\
  [https://api.openalex.org/funders?filter=country\_code:ca](https://api.openalex.org/funders?filter=country\_code:ca)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query
{% endhint %}

### `/funders` attribute filters

You can filter using these attributes of the `Funder` entity object (click each one to view their documentation on the [`Funder`](funder-object.md) object page):

* [`cited_by_count`](funder-object.md#cited\_by\_count)
* [`country_code`](funder-object.md#country\_code)
* [`grants_count`](funder-object.md#grants_count)
* [`ids.openalex`](funder-object.md#ids) (alias: `openalex`)
* [`ids.ror`](funder-object.md#ids) (alias: `ror`)
* [`ids.wikidata`](funder-object.md#ids) (alias: `wikidata`)
* [`summary_stats.2yr_mean_citedness`](funder-object.md#summary_stats) (accepts float, null, !null, can use range queries such as < >)
* [`summary_stats.h_index`](funder-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`summary_stats.i10_index`](funder-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`works_count`](funder-object.md#works\_count)

### `/funders` convenience filters

These filters aren't attributes of the [`Funder`](funder-object.md) object, but they're included to address some common use cases:

#### `continent`

Value: a String with a valid [continent filter](../geo/continents.md#filter-by-continent)

Returns: funders that are located in the chosen continent.

* Get funders that are located in South America\
  [`https://api.openalex.org/funders?filter=continent:south\_america`](https://api.openalex.org/funders?filter=continent:south\_america)

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](./search-funders.md#search-funders) for Funders.

#### `description.search`

Value: a search string

Returns: funders with a [`description`](funder-object.md#description) containing the given string; see the [search page](search-funders.md#search-a-specific-field) for details.

* Get funders with description containing "health":\
  [`https://api.openalex.org/funders?filter=description.search:health`](https://api.openalex.org/funders?filter=description.search:health)

#### `display_name.search`

Value: a search string

Returns: funders with a [`display_name`](funder-object.md#display\_name) containing the given string; see the [search page](search-funders.md#search-a-specific-field) for details.

* Get funders with names containing "health":\
  [`https://api.openalex.org/funders?filter=display_name.search:health`](https://api.openalex.org/funders?filter=display_name.search:health)

{% hint style="info" %}
In most cases, you should use the [`search` parameter](search-funders.md) instead of this filter because it uses a better search algorithm.
{% endhint %}

#### `is_global_south`

Value: a Boolean (`true` or `false`)

Returns: funders that are located in the [Global South](../geo/regions.md#global-south).

* Get funders that are located in the Global South\
  [https://api.openalex.org/funders?filter=is\_global\_south:true](https://api.openalex.org/funders?filter=is\_global\_south:true)

