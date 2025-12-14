# Search awards

The best way to search for awards is to use the `search` query parameter, which searches across the [`display_name`](award-object.md#display_name) and [`description`](award-object.md#description) fields.

* Get awards that mention "machine learning":\
  [`https://api.openalex.org/awards?search=machine%20learning`](https://api.openalex.org/awards?search=machine%20learning)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated and how words are stemmed to improve search results.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, append `.search` to the end of the property you're filtering for:

* Get awards where the display name includes "climate":\
  [`https://api.openalex.org/awards?filter=display_name.search:climate`](https://api.openalex.org/awards?filter=display_name.search:climate)

The following fields can be searched as a filter within awards:

| Search filter                                               | Field that is searched                         |
| ----------------------------------------------------------- | ---------------------------------------------- |
| [`display_name.search`](filter-awards.md#display_name.search) | [`display_name`](award-object.md#display_name) |
| [`description.search`](filter-awards.md#description.search)   | [`description`](award-object.md#description)   |

You can also use the filter `default.search`, which works the same as using the `search` parameter.
