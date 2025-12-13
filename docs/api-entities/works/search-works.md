# Search works

The best way to search for works is to use the `search` query parameter, which searches across [titles](work-object/#title), [abstracts](work-object/#abstract\_inverted\_index), and [fulltext](work-object/README.md#has_fulltext). Example:

* Get works with search term "dna" in the title, abstract, or fulltext:\
  [`https://api.openalex.org/works?search=dna`](https://api.openalex.org/works?search=dna)

Fulltext search is available for a subset of works, see [`Work.has_fulltext`](./work-object/README.md#has_fulltext) for more details.

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Search a specific field

You can use search as a [filter](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md), allowing you to fine-tune the fields you're searching over. To do this, you append `.search` to the end of the property you are filtering for:

* Get works with "cubist" in the title:\
  [`https://api.openalex.org/works?filter=title.search:cubist`](https://api.openalex.org/works?filter=title.search:cubist)

The following fields can be searched within works:

| Search filter                                                                        | Field that is searched                                                  |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| [`abstract.search`](filter-works.md#abstract.search)                                 | [`abstract_inverted_index`](work-object/#abstract\_inverted\_index)     |
| [`display_name.search`](filter-works.md#display\_name.search-alias-title.search)     | [`display_name`](work-object/#display\_name)                            |
| [`fulltext.search`](filter-works.md#fulltext.search)                                 | fulltext via [`n-grams`](get-n-grams.md)                                |
| [`raw_affiliation_strings.search`](filter-works.md#raw_affiliation_stringssearch)      | [`authorships.raw_affiliation_strings`](./work-object/authorship-object.md#raw_affiliation_strings)  |
| [`title.search`](filter-works.md#display\_name.search-alias-title.search)            | [`display_name`](work-object/#display\_name)                            |
| [`title_and_abstract.search`](filter-works.md#title_and_abstractsearch)            | [`display_name`](work-object/#display\_name) and [`abstract_inverted_index`](work-object/#abstract\_inverted\_index)  |

You can also use the filter `default.search`, which works the same as using the [`search` parameter](#search-works).

These searches make use of stemming and stop-word removal. You can disable this for searches on titles and abstracts. Learn how to do this [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md#search-without-stemming).

### Why can't I search by name of related entity (author name, institution name, etc.)?

Rather than searching for the _names_ of entities related to works—such as authors, institutions, and sources—you need to search by a more unique identifier for that entity, like the OpenAlex ID. This means that there is a 2 step process:

1. Find the ID of the related entity. For example, if you're interested in works associated with NYU, you could search the `/institutions` endpoint for that name: [`https://api.openalex.org/institutions?search=nyu`](https://api.openalex.org/institutions?search=nyu). Looking at the first result, you'll see that the OpenAlex ID for NYU is `I57206974`.
2. Use a [filter ](filter-works.md)with the `/works` endpoint to get all of the works: [`https://api.openalex.org/works?filter=institutions.id:I57206974`](https://api.openalex.org/works?filter=institutions.id:I57206974).

Why can't you do this in just one step? Well, if you use the search term, "NYU," you might end up missing the ones that use the full name "New York University," rather than the initials. Sure, you could try to think of all possible variants and search for all of them, but you might miss some, and you risk putting in search terms that let in works that you're not interested in. Figuring out which works are actually associated with the "NYU" you're interested shouldn't be your responsibility—that's our job! We've done that work for you, so all the relevant works should be associated with one unique ID.

## Autocomplete works

You can autocomplete works to create a very fast type-ahead style search function:

* Autocomplete works with "tigers" in the title:\
  [`https://api.openalex.org/autocomplete/works?q=tigers`](https://api.openalex.org/autocomplete/works?q=tigers)

This returns a list of works titles with the author of each work set as the hint:

<pre class="language-json"><code class="lang-json">{ 
  "results": [
    {
      "id": "https://openalex.org/W2125098916",
      "display_name": "Crouching tigers, hidden prey: Sumatran tiger and prey populations in a tropical forest landscape",
      "hint": "Timothy G. O'Brien, Margaret F. Kinnaird, Hariyo T. Wibisono",
      "cited_by_count": 620,
      "works_count": null,
      "entity_type": "work",
      "external_id": "https://doi.org/10.1017/s1367943003003172"
    },
    ...
<strong>  ]
</strong><strong>}
</strong></code></pre>

{% hint style="info" %}
Read more about [autocomplete](../../how-to-use-the-api/get-lists-of-entities/autocomplete-entities.md).
{% endhint %}
