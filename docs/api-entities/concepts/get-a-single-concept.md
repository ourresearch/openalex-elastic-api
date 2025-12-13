# Get a single concept

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

It's easy to get a concept from the API with: `/concepts/<entity_id>`. Here's an example:

* Get the concept with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `C71924100`:\
  [https://api.openalex.org/concepts/C71924100](https://api.openalex.org/concepts/C71924100)

That will return a [`Concept`](../concepts/concept-object.md) object, describing everything OpenAlex knows about the concept with that ID:

```json
{
    "id": "https://openalex.org/C71924100",
    "wikidata": "https://www.wikidata.org/wiki/Q11190",
    "display_name": "Medicine",
    "level": 0,
    "description": "field of study for diagnosing, treating and preventing disease",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### External IDs

You can look up concepts using external IDs such as a wikidata ID:

* Get the concept with wikidata ID Q11190:\
  [https://api.openalex.org/concepts/wikidata:Q11190](https://api.openalex.org/concepts/wikidata:Q11190)

Available external IDs for concepts are:

| External ID                    | URN        |
| ------------------------------ | ---------- |
| Microsoft Academic Graph (MAG) | `mag`      |
| Wikidata                       | `wikidata` |

### Select fields

You can use `select` to limit the fields that are returned in a concept object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a concept object\
  [https://api.openalex.org/concepts/C71924100?select=id,display\_name](https://api.openalex.org/concepts/C71924100?select=id,display\_name)
