# Search topics

The best way to search for topics is to use the `search` query parameter, which searches the [`display_name`](../topics/topic-object.md#display\_name), [`description`](../topics/topic-object.md#description), and [`keyword`](./topic-object.md#keywords) fields. Example:

* Search topics' `display_name` and `description` for "artificial intelligence":\
  [https://api.openalex.org/topics?search=artificial intelligence](https://api.openalex.org/topics?search=artificial%20intelligence)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can also use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get topics with "medical" in the `display_name`:\
  [https://api.openalex.org/topics?filter=display_name.search:medical](https://api.openalex.org/topics?filter=display_name.search:medical)

The following fields can be searched as a filter within topics:

| Search filter                                                                  | Field that is searched                                          |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [`display_name.search`](../topics/filter-topics.md#display\_name.search) | [`display_name`](../topics/topic-object.md#display\_name) |
| [`description.search`](../topics/filter-topics.md#description.search) | [`description`](../topics/topic-object.md#description) |
| [`keywords.search`](../topics/filter-topics.md#keywords.search) | [`keywords`](../topics/topic-object.md#keywords) |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](search-topics.md#search-topics).
