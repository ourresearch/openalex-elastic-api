# Get a single publisher

It's easy to get a publisher from from the API with: `/publishers/<entity_id>`. Here's an example:

* Get the publisher with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `P4310319965`: \
  [https://api.openalex.org/publishers/P4310319965](https://api.openalex.org/publishers/P4310319965)

That will return a [`Publisher`](publisher-object.md) object, describing everything OpenAlex knows about the publisher with that ID:

```json
{
  "id": "https://openalex.org/P4310319965",
  "display_name": "Springer Nature",
  "alternate_titles": [
    "エイプレス",
    "Springer Nature Group",
    "施普林格-自然出版集团"
  ],
  "hierarchy_level": 0,
  // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### External IDs

You can look up publishers using external IDs such as a Wikidata ID:

* Get the publisher with Wikidata ID Q1479654:\
  [https://api.openalex.org/publishers/wikidata:Q1479654](https://api.openalex.org/publishers/wikidata:Q1479654)

Available external IDs for publishers are:

| External ID | URN        |
| ----------- | ---------- |
| ROR         | `ror`      |
| Wikidata    | `wikidata` |

### Select fields

You can use `select` to limit the fields that are returned in a publisher object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a publisher object\
  [https://api.openalex.org/publishers/P4310319965?select=id,display\_name](https://api.openalex.org/publishers/P4310319965?select=id,display\_name)
