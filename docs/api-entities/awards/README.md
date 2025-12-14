---
description: Grants and awards that fund research
---

# 🏆 Awards

Awards are grants or funding awards that support research. OpenAlex indexes awards from multiple sources including Crossref grant metadata and other funding databases.

* Get a list of OpenAlex awards:\
  [`https://api.openalex.org/awards`](https://api.openalex.org/awards)

Awards are connected to works through the [`awards`](../works/work-object/#awards) property, and to funders through the [`funder`](award-object.md#funder) property.

{% hint style="info" %}
The `awards` entity, along with the [`funders`](../funders/) property on works, replaces the older `grants` property which has been removed. These new entities provide much more comprehensive funding data.
{% endhint %}

## What's next

Learn more about what you can do with awards:

* [The Award object](award-object.md)
* [Get a single award](get-a-single-award.md)
* [Get lists of awards](get-lists-of-awards.md)
* [Filter awards](filter-awards.md)
* [Search awards](search-awards.md)
* [Group awards](group-awards.md)
