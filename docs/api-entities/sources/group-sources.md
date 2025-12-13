# Group sources

You can group sources with the `group_by` parameter:

* Get counts of sources by publisher:\
  [https://api.openalex.org/sources?group\_by=publisher](https://api.openalex.org/sources?group\_by=publisher)

Or you can group using one the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the number of results returned, and how to sort results.
{% endhint %}

### `/sources` group\_by attributes

* [`apc_prices.currency`](source-object.md#apc\_prices)
* [`apc_usd`](source-object.md#apc\_usd)
* [`cited_by_count`](source-object.md#cited\_by\_count)
* [`has_issn`](filter-sources.md#has\_issn)
* [`continent`](../geo/continents.md#group-by-continent)
* [`country_code`](source-object.md#country\_code)
* [`host_organization`](source-object.md#host\_organization) (alias: `host_organization.id`)
* [`host_organization_lineage`](source-object.md#host_organization_lineage) (alias: `host_organization.id`)
* [`is_global_south`](../geo/regions.md#group-by-global-south)
* [`is_core`](source-object.md#is_core)
* [`is_in_doaj`](source-object.md#is\_in\_doaj)
* [`is_oa`](source-object.md#is\_oa)
* [`issn`](source-object.md#issn)
* [`publisher`](source-object.md#publisher)
* [`summary_stats.2yr_mean_citedness`](source-object.md#summary_stats)
* [`summary_stats.h_index`](source-object.md#summary_stats)
* [`summary_stats.i10_index`](source-object.md#summary_stats)
* [`type`](source-object.md#type)
* [`works_count`](source-object.md#works\_count)
