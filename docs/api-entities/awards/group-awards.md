# Group awards

You can group awards with the `group_by` parameter:

* Get counts of awards by funder:\
  [`https://api.openalex.org/awards?group_by=funder.id`](https://api.openalex.org/awards?group_by=funder.id)

Or you can group using one of the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the ## default limit of 200 results per call, and how to sort results.
{% endhint %}

## `/awards` group_by attributes

* [`currency`](award-object.md#currency)
* [`end_year`](award-object.md#end_year)
* [`funder.id`](award-object.md#funder)
* [`funder_scheme`](award-object.md#funder_scheme)
* [`funding_type`](award-object.md#funding_type)
* [`lead_investigator.affiliation.country`](award-object.md#lead_investigator)
* [`provenance`](award-object.md#provenance)
* [`start_year`](award-object.md#start_year)
