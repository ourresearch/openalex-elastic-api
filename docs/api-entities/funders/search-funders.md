# Search funders

The best way to search for funders is to use the `search` query parameter, which searches the [`display_name`](funder-object.md#display\_name), the [`alternate_titles`](funder-object.md#alternate\_titles), and the [`description`](funder_object.md#description) fields. Example:

* Search funders' `display_name`, `alternate_titles`, and `description` for "health":\
  [`https://api.openalex.org/funders?search=health`](https://api.openalex.org/funders?search=health)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get funders with "florida" in the `display_name`:\
  [`https://api.openalex.org/funders?filter=display_name.search:florida`](https://api.openalex.org/funders?filter=display_name.search:florida)

The following fields can be searched as a filter within funders:

| Search filter                                                        | Field that is searched                                |
| -------------------------------------------------------------------- | ----------------------------------------------------- |
| [`display_name.search`](filter-funders.md#display_name.search) | [`display_name`](funder-object.md#display_name) |
| [`description.search`](filter-funders.md#description.search) | [`description`](funder-object.md#description) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](#search-funders).

## Autocomplete funders

You can autocomplete funders to create a very fast type-ahead style search function:

* Autocomplete funders with "national sci" in the [`display_name`](funder-object.md#display_name):\
  [https://api.openalex.org/autocomplete/funders?q=national+sci](https://api.openalex.org/autocomplete/funders?q=national+sci)

This returns a list of funders with the funder location set as the hint:

```json
  "results": [
    {
        "id": "https://openalex.org/F4320306076",
        "display_name": "National Science Foundation",
        "hint": null,
        "cited_by_count": 6705777,
        "works_count": 264303,
        "entity_type": "funder",
        "external_id": "https://ror.org/021nxhr62"
    },
    ...
  ]
```

{% hint style="info" %}
Read more in the [autocomplete page](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md) in the API guide.
{% endhint %}
