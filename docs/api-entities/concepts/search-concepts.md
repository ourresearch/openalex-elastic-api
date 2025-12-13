# Search concepts

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

The best way to search for concepts is to use the `search` query parameter, which searches the [`display_name`](../concepts/concept-object.md#display\_name) and [`description`](../concepts/concept-object.md#description) fields. Example:

* Search concepts' `display_name` and `description` for "artificial intelligence":\
  [https://api.openalex.org/concepts?search=artificial intelligence](https://api.openalex.org/concepts?search=artificial%20intelligence)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get concepts with "medical" in the `display_name`:\
  [https://api.openalex.org/concepts?filter=display\_name.search:medical](https://api.openalex.org/concepts?filter=display\_name.search:medical)

The following field can be searched as a filter within concepts:

| Search filter                                                                  | Field that is searched                                          |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [`display_name.search`](../concepts/filter-concepts.md#display\_name.search) | [`display_name`](../concepts/concept-object.md#display\_name) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](search-concepts.md#search-concepts).

## Autocomplete concepts

You can autocomplete concepts to create a very fast type-ahead style search function:

* Autocomplete concepts with "comp" in the `display_name`:\
  [https://api.openalex.org/autocomplete/concepts?q=comp](https://api.openalex.org/autocomplete/concepts?q=comp)

This returns a list of concepts with the description set as the hint:

<pre class="language-json"><code class="lang-json">{ 
  "results": [
    {
        "id": "https://openalex.org/C41008148",
        "display_name": "Computer science",
        "hint": "theoretical study of the formal foundation enabling the automated processing or computation of information, for example on a computer or over a data transmission network",
        "cited_by_count": 392939277,
        "works_count": 76722605,
        "entity_type": "concept",
        "external_id": "https://www.wikidata.org/wiki/Q21198"
    },
    ...
<strong>  ]
</strong><strong>}
</strong></code></pre>

{% hint style="info" %}
Read more in the [autocomplete page](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md) in the API guide.
{% endhint %}
