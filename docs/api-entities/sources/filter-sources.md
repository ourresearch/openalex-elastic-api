# Filter sources

You can filter sources with the `filter` parameter:

* Get sources that have an ISSN\
  [`https://api.openalex.org/sources?filter=has_issn:true`](https://api.openalex.org/sources?filter=has\_issn:true)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query
{% endhint %}

### `/sources` attribute filters

You can filter using these attributes of the `Source` entity object (click each one to view their documentation on the [`Source`](source-object.md) object page):

* [`apc_prices.currency`](source-object.md#apc\_prices)
* [`apc_prices.price`](source-object.md#apc\_prices)
* [`apc_usd`](source-object.md#apc\_usd)
* [`cited_by_count`](source-object.md#cited\_by\_count)
* [`country_code`](source-object.md#country\_code)
* [`host_organization`](source-object.md#host\_organization) (alias: `host_organization.id`)
* [`host_organization_lineage`](source-object.md#host_organization_lineage) — Use this with a publisher ID to find works from that publisher and all of its children.
* [`ids.openalex`](source-object.md#ids) (alias: `openalex`)
* [`is_core`](source-object.md#is_core)
* [`is_in_doaj`](source-object.md#is\_in\_doaj)
* [`is_oa`](source-object.md#is\_oa)
* [`issn`](source-object.md#issn)
* [`publisher`](source-object.md#publisher) — Requires exact match. Use the [`host_organization_lineage`](source-object.md#host_organization_lineage) filter instead if you want to find works from a publisher and all of its children.
* [`summary_stats.2yr_mean_citedness`](source-object.md#summary_stats) (accepts float, null, !null, can use range queries such as < >)
* [`summary_stats.h_index`](source-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`summary_stats.i10_index`](source-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`type`](source-object.md#type)
* [`works_count`](source-object.md#works\_count)
* [`x_concepts.id`](source-object.md#x\_concepts) (alias: `concepts.id` or `concept.id`) -- will be deprecated soon

{% hint style="info" %}
Want to filter by `host_organization.display_name`? This is a two-step process:

1. Find the host organization's ID by searching by `display_name` in Publishers or Institutions, depending on which type you are looking for.
2. Filter works by `host_organization.id`.

To learn more about why we do it this way, [see here.](../works/search-works.md#why-cant-i-search-by-name-of-related-entity-author-name-institution-name-etc.)
{% endhint %}

### `/sources` convenience filters

These filters aren't attributes of the [`Source`](source-object.md) object, but they're included to address some common use cases:

#### `continent`

Value: a String with a valid [continent filter](../geo/continents.md#filter-by-continent)

Returns: sources that are associated with the chosen continent.

* Get sources that are associated with Asia\
  [`https://api.openalex.org/sources?filter=continent:asia`](https://api.openalex.org/sources?filter=continent:asia)

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](./search-sources.md#search-sources) for Sources.

#### `display_name.search`

Value: a search string

Returns: sources with a [`display_name`](source-object.md#display\_name) containing the given string; see the [search page](search-sources.md) for details.

* Get sources with names containing "Neurology":\
  [`https://api.openalex.org/sources?filter=display_name.search:Neurology`](https://api.openalex.org/sources?filter=display\_name.search:Neurology)``

{% hint style="info" %}
In most cases, you should use the [`search`](search-sources.md#sources-full-search) parameter instead of this filter because it uses a better search algorithm.
{% endhint %}

#### `has_issn`

Value: a Boolean (`true` or `false`)

Returns: sources that have or lack an [ISSN](./source-object.md#issn), depending on the given value.

* Get sources without ISSNs:\
  [`https://api.openalex.org/sources?filter=has_issn:false`](https://api.openalex.org/sources?filter=has\_issn:false)``

#### `is_global_south`

Value: a Boolean (`true` or `false`)

Returns: sources that are associated with the [Global South](../geo/regions.md#global-south).

* Get sources that are located in the Global South\
  [`https://api.openalex.org/sources?filter=is\_global\_south:true`](https://api.openalex.org/sources?filter=is\_global\_south:true)
