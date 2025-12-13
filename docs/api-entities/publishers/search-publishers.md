# Search publishers

The best way to search for publishers is to use the `search` query parameter, which searches the [`display_name`](publisher-object.md#display\_name) and [`alternate_titles`](publisher-object.md#alternate\_titles) fields. Example:

* Search publishers' `display_name` and `alternate_titles` for "springer":\
  [https://api.openalex.org/publishers?search=springer](https://api.openalex.org/publishers?search=springer)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get publishers with "elsevier" in the `display_name`:\
  https://api.openalex.org/publishers?filter=display\_name.search:elsevier

The following field can be searched as a filter within publishers:

| Search filter                                                      | Field that is searched                              |
| ------------------------------------------------------------------ | --------------------------------------------------- |
| [`display_name.search`](filter-publishers.md#display\_name.search) | [`display_name`](publisher-object.md#display\_name) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](#search-publishers).

## Autocomplete publishers

You can autocomplete publishers to create a very fast type-ahead style search function:

* Autocomplete publishers with "els" in the `display_name`:\
  [https://api.openalex.org/autocomplete/publishers?q=els](https://api.openalex.org/autocomplete/publishers?q=els)

This returns a list of publishers:

<pre class="language-json"><code class="lang-json">{ 
  "results": [
    {
        "id": "https://openalex.org/P4310320990",
        "display_name": "Elsevier BV",
        "hint": null,
        "cited_by_count": 407508754,
        "works_count": 20311868,
        "entity_type": "publisher",
        "external_id": "https://www.wikidata.org/entity/Q746413"
    },
    ...
<strong>  ]
</strong><strong>}
</strong></code></pre>

{% hint style="info" %}
Read more in the [autocomplete page](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md) in the API guide.
{% endhint %}
