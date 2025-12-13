# Get a single source

It's easy to get a source from from the API with: `/sources/<entity_id>`. Here's an example:

* Get the source with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `S137773608`: \
  [https://api.openalex.org/sources/S137773608](https://api.openalex.org/sources/S137773608)

That will return an [`Source`](source-object.md) object, describing everything OpenAlex knows about the source with that ID:

```json
{
    "id": "https://openalex.org/S137773608",
    "issn_l": "0028-0836",
    "issn": [
        "1476-4687",
        "0028-0836"
    ],
    "display_name": "Nature",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

{% hint style="info" %}
Sources are also available via an alias: `/journals`
{% endhint %}

### External IDs

You can look up journals using external IDs such as an ISSN:

* Get the source with ISSN: `2041-1723`:\
  [`https://api.openalex.org/sources/issn:2041-1723`](https://api.openalex.org/sources/issn:2041-1723)

Available external IDs for sources are:

| External ID                    | URN        |
| ------------------------------ | ---------- |
| ISSN                           | `issn`     |
| Fatcat                         | `fatcat`   |
| Microsoft Academic Graph (MAG) | `mag`      |
| Wikidata                       | `wikidata` |

### Select fields

You can use `select` to limit the fields that are returned in a source object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a source object\
  [https://api.openalex.org/sources/S137773608?select=id,display\_name](https://api.openalex.org/sources/S137773608?select=id,display\_name)
