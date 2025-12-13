# Filter authors

You can filter authors with the `filter` parameter:

* Get authors that have an ORCID\
  [https://api.openalex.org/authors?filter=has\_orcid:true](https://api.openalex.org/authors?filter=has\_orcid:true)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query.
{% endhint %}

### `/authors` attribute filters

You can filter using these attributes of the `Author` entity object (click each one to view their documentation on the [`Author`](author-object.md) object page):

* [`affiliations.institution.country_code`](./author-object.md#affiliations)
* [`affiliations.institution.id`](./author-object.md#affiliations)
* [`affiliations.institution.lineage`](./author-object.md#affiliations)
* [`affiliations.institution.ror`](./author-object.md#affiliations)
* [`affiliations.institution.type`](./author-object.md#affiliations)
* [`cited_by_count`](author-object.md#cited\_by\_count)
* [`ids.openalex`](author-object.md#ids) (alias: `openalex`)
* [`last_known_institution.country_code`](author-object.md#last\_known\_institution)
* [`last_known_institution.id`](author-object.md#last\_known\_institution)
* [`last_known_institution.lineage`](author-object.md#last\_known\_institution)
* [`last_known_institution.ror`](author-object.md#last\_known\_institution)
* [`last_known_institution.type`](author-object.md#last\_known\_institution)
* [`orcid`](author-object.md#orcid)
* [`scopus`](author-object.md#ids) (the author's scopus ID, as an integer)
* [`summary_stats.2yr_mean_citedness`](author-object.md#summary_stats) (accepts float, null, !null, can use range queries such as < >)
* [`summary_stats.h_index`](author-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`summary_stats.i10_index`](author-object.md#summary_stats) (accepts integer, null, !null, can use range queries)
* [`works_count`](author-object.md#works\_count)
* [`x_concepts.id`](author-object.md#x\_concepts) (alias: `concepts.id` or `concept.id`) -- will be deprecated soon

{% hint style="info" %}
Want to filter by `last_known_institution.display_name`? This is a two-step process:

1. Find the `institution.id` by searching institutions by `display_name`.
2. Filter works by `last_known_institution.id`.

To learn more about why we do it this way, [see here.](../works/search-works.md#why-cant-i-search-by-name-of-related-entity-author-name-institution-name-etc.)
{% endhint %}

### `/authors` convenience filters

These filters aren't attributes of the [`Author` object](author-object.md), but they're included to address some common use cases:

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](./search-authors.md#search-authors) for Authors.

#### `display_name.search`

Value: a search string

Returns: Authors whose [`display_name`](author-object.md#display\_name) contains the given string; see the [search filter](search-authors.md#search-a-specific-field) for details.

* Get authors named "tupolev":\
  [`https://api.openalex.org/authors?filter=display_name.search:tupolev`](https://api.openalex.org/authors?filter=display\_name.search:tupolev)

#### `has_orcid`

Value: a Boolean (`true` or `false`)

Returns: authors that have or lack an [orcid](author-object.md#orcid), depending on the given value.

* Get the authors that have an ORCID:\
  ``[`https://api.openalex.org/authors?filter=has_orcid:true`](https://api.openalex.org/authors?filter=has\_orcid:true)

#### `last_known_institution.continent`

Value: a String with a valid [continent filter](../geo/continents.md#filter-by-continent)

Returns: authors where where the last known institution is in the chosen continent.

* Get authors where the last known institution is located in Africa\
  [https://api.openalex.org/authors?filter=last\_known\_institution.continent:africa](https://api.openalex.org/authors?filter=last\_known\_institution.continent:africa)

#### `last_known_institution.is_global_south`

Value: a Boolean (`true` or `false`)

Returns: works where at least _one_ of the author's institutions is in the [Global South](../geo/regions.md#global-south).

* Get authors where the last known institution is located in the Global South\
  [https://api.openalex.org/authors?filter=last\_known\_institution.is\_global\_south:true](https://api.openalex.org/authors?filter=last\_known\_institution.is\_global\_south:true)
