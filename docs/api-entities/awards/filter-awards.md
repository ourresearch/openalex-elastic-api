# Filter awards

You can filter awards with the `filter` parameter:

* Get awards from the National Science Foundation:\
  [`https://api.openalex.org/awards?filter=funder.id:F4320306076`](https://api.openalex.org/awards?filter=funder.id:F4320306076)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query.
{% endhint %}

## `/awards` attribute filters

You can filter using these attributes of the [`Award`](award-object.md) object:

* [`amount`](award-object.md#amount)
* [`currency`](award-object.md#currency)
* [`doi`](award-object.md#doi)
* [`end_year`](award-object.md#end_year)
* [`funder.doi`](award-object.md#funder)
* [`funder.id`](award-object.md#funder)
* [`funder.ror`](award-object.md#funder)
* [`funder_award_id`](award-object.md#funder_award_id)
* [`funder_name`](award-object.md#funder)
* [`funder_scheme`](award-object.md#funder_scheme)
* [`funded_outputs`](award-object.md#funded_outputs)
* [`funded_outputs_count`](award-object.md#funded_outputs_count)
* [`funding_type`](award-object.md#funding_type)
* [`id`](award-object.md#id)
* [`lead_investigator.affiliation.country`](award-object.md#lead_investigator)
* [`lead_investigator.affiliation.name`](award-object.md#lead_investigator)
* [`lead_investigator.family_name`](award-object.md#lead_investigator)
* [`lead_investigator.given_name`](award-object.md#lead_investigator)
* [`lead_investigator.orcid`](award-object.md#lead_investigator)
* [`provenance`](award-object.md#provenance)
* [`start_year`](award-object.md#start_year)

## `/awards` convenience filters

These filters aren't attributes of the [`Award`](award-object.md) object, but they're included to address some common use cases:

### `default.search`

Value: a search string

This works the same as using the [`search` parameter](search-awards.md) for awards.

### `display_name.search`

Value: a search string

Returns awards with a [`display_name`](award-object.md#display_name) containing the given string.

* Get awards with "climate" in the name:\
  [`https://api.openalex.org/awards?filter=display_name.search:climate`](https://api.openalex.org/awards?filter=display_name.search:climate)

### `description.search`

Value: a search string

Returns awards with a [`description`](award-object.md#description) containing the given string.
