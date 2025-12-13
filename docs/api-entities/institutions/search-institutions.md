# Search institutions

The best way to search for institutions is to use the `search` query parameter, which searches the [`display_name`](institution-object.md#display\_name), the [`display_name_alternatives`](./institution-object.md#display_name_alternatives), and the [`display_name_acronyms`](./institution-object.md#display_name_acronyms). Example:

* Search institutions for San Diego State University:\
  [`https://api.openalex.org/institutions?search=san diego state university`](https://api.openalex.org/institutions?search=san%20diego%20state%20university)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get institutions with "florida" in the `display_name`:\
  [https://api.openalex.org/institutions?filter=display\_name.search:florida](https://api.openalex.org/institutions?filter=display\_name.search:florida)

The following field can be searched as a filter within institutions:

| Search filter                                                        | Field that is searched                                |
| -------------------------------------------------------------------- | ----------------------------------------------------- |
| [`display_name.search`](filter-institutions.md#display\_name.search) | [`display_name`](institution-object.md#display\_name) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](#search-institutions).

## Autocomplete institutions

You can autocomplete institutions to create a very fast type-ahead style search function:

* Autocomplete institutions with "harv" in the [`display_name`](institution-object.md#display\_name):\
  [https://api.openalex.org/autocomplete/institutions?q=harv](https://api.openalex.org/autocomplete/institutions?q=harv)

This returns a list of institutions with the institution location set as the hint:

<pre class="language-json"><code class="lang-json">{ 
  "results": [
    {
        "id": "https://openalex.org/I136199984",
        "display_name": "Harvard University",
        "hint": "Cambridge, USA",
        "cited_by_count": 37792327,
        "works_count": 242547,
        "entity_type": "institution",
        "external_id": "https://ror.org/03vek6s52"
    },
    ...
<strong>  ]
</strong><strong>}
</strong></code></pre>

{% hint style="info" %}
Read more in the [autocomplete page](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md) in the API guide.
{% endhint %}
