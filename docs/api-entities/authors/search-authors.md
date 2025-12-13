# Search authors

The best way to search for authors is to use the `search` query parameter, which searches the [`display_name`](./author-object.md#display_name) and the [`display_name_alternatives`](./author-object.md#display_name_alternatives) fields. Example:

* Get works with the author name "Carl Sagan":\
  [`https://api.openalex.org/authors?search=carl sagan`](https://api.openalex.org/authors?search=carl%20sagan)

Searching without a middle initial returns names with _and_ without middle initials. So a search for "John Smith" will also return "John W. Smith".&#x20;

Names with diacritics are flexible as well. So a search for David Tarrago can return David Tarragó, and a search for David Tarragó can return David Tarrago. When searching with a diacritic, diacritic versions of the names are prioritized in order to honor the original form of the author's name. Read more about our handling of diacritics [here](https://blog.ourresearch.org/author-search-in-openalex-improved-handling-of-diacritics-within-names/).

{% hint style="info" %}
You can read more in the [search page](../../how-to-use-the-api/get-lists-of-entities/search-entities.md) in the API Guide. It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), by appending `.search` to the end of the property you are filtering for:

* Get authors with the name "john smith" in the display\_name:\
  [`https://api.openalex.org/authors?filter=display\_name.search:john smith`](https://api.openalex.org/authors?filter=display\_name.search:john%20smith)

When searching for authors, there is no difference when using the `search` parameter or the filter `display_name.search`, since display\_name is the only field searched when finding authors.

| Search filter                                                   | Field that is searched                           |
| --------------------------------------------------------------- | ------------------------------------------------ |
| [`display_name.search`](filter-authors.md#display\_name.search) | [`display_name`](author-object.md#display\_name) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](#search-authors).

## Autocomplete authors

You can autocomplete authors to create a very fast type-ahead style search function:

* Autocomplete authors with "ronald sw" in the display name:\
  [`https://api.openalex.org/autocomplete/authors?q=ronald sw`](https://api.openalex.org/autocomplete/authors?q=ronald%20sw)

This returns a list of authors with their last known affiliated institution as the hint:

<pre class="language-json"><code class="lang-json">{ 
  "results": [
      {
          "id": "https://openalex.org/A5007433649",
          "display_name": "Ronald Swanstrom",
          "hint": "University of North Carolina at Chapel Hill, USA",
          "cited_by_count": 19142,
          "works_count": 339,
          "entity_type": "author",
          "external_id": "https://orcid.org/0000-0001-7777-0773",
          "filter_key": "authorships.author.id"
       },
       ...
<strong>  ]
</strong><strong>}
</strong></code></pre>

{% hint style="info" %}
Read more about [autocomplete](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md).
{% endhint %}
