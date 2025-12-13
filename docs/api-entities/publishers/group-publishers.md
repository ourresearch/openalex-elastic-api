# Group publishers

You can group publishers with the `group_by` parameter:

* Get counts of publishers by [`country_codes`](publisher-object.md#country\_codes):\
  [`https://api.openalex.org/publishers?group\_by=country\_codes`](https://api.openalex.org/publishers?group\_by=country\_codes)

Or you can group using one the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the number of results returned, and how to sort results.
{% endhint %}

### `/publishers` group_by attributes

* [`country_codes`](publisher-object.md#country\_codes)
* [`hierarchy_level`](publisher-object.md#hierarchy\_level)
* [`lineage`](publisher-object.md#lineage)
* [`summary_stats.2yr_mean_citedness`](publisher-object.md#summary_stats)
* [`summary_stats.h_index`](publisher-object.md#summary_stats)
* [`summary_stats.i10_index`](publisher-object.md#summary_stats)
