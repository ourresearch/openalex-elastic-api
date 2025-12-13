# Get a single funder

It's easy to get a funder from from the API with: `/funders/<entity_id>`. Here's an example:

* Get the funder with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `F4320332161`: \
  [https://api.openalex.org/funders/F4320332161](https://api.openalex.org/funders/F4320332161)

That will return a [`Funder`](funder-object.md) object, describing everything OpenAlex knows about the funder with that ID:

```json
{
  "id": "https://openalex.org/F4320332161",
  "display_name": "National Institutes of Health",
  "alternate_titles": [
  "US National Institutes of Health",
  "Institutos Nacionales de la Salud",
  "NIH"
  ],
  // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### External IDs

You can look up funders using external IDs such as a Wikidata ID:

* Get the funder with Wikidata ID Q1479654:\
  [`https://api.openalex.org/funders/wikidata:Q390551`](https://api.openalex.org/funders/wikidata:Q390551)

Available external IDs for funders are:

| External ID | URN        |
| ----------- | ---------- |
| ROR         | `ror`      |
| Wikidata    | `wikidata` |

### Select fields

You can use `select` to limit the fields that are returned in a funder object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a funder object\
  [`https://api.openalex.org/funders/F4320332161?select=id,display_name`](https://api.openalex.org/funders/F4320332161?select=id,display_name)

