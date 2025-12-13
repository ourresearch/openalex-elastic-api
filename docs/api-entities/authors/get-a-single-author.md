# Get a single author

It's easy to get an author from from the API with: `/authors/<entity_id>`. Here's an example:

* Get the author with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `A5023888391`: \
  [`https://api.openalex.org/authors/A5023888391`](https://api.openalex.org/authors/A5023888391)

That will return an [`Author`](author-object.md) object, describing everything OpenAlex knows about the author with that ID:

```json
{
    "id": "https://openalex.org/A5023888391",
    "orcid": "https://orcid.org/0000-0001-6187-6610",
    "display_name": "Jason Priem",
    "display_name_alternatives": [],
    "works_count": 53,
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

{% hint style="info" %}
Authors are also available via an alias: `/people`
{% endhint %}

## External IDs

You can look up authors using external IDs such as an ORCID:

* Get the author with this ORCID: `https://orcid.org/0000-0002-1298-3089`:\
  [`https://api.openalex.org/authors/https://orcid.org/0000-0002-1298-3089`](https://api.openalex.org/authors/https://orcid.org/0000-0002-1298-3089)

You can use the full ID or a shorter Uniform Resource Name (URN) format like so:\
  [`https://api.openalex.org/authors/orcid:0000-0002-1298-3089`](https://api.openalex.org/authors/orcid:0000-0002-1298-3089)

Available external IDs for authors are:

| External ID                    | URN         |
| ------------------------------ | ----------- |
| ORCID                          | `orcid`     |
| Scopus                         | `scopus`    |
| Twitter                        | `twitter`   |
| Wikipedia                      | `wikipedia` |

## Select fields

You can use `select` to limit the fields that are returned in an author object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` and orcid for an author object\
  [`https://api.openalex.org/authors/A5023888391?select=id,display_name,orcid`](https://api.openalex.org/authors/A5023888391?select=id,display\_name,orcid)
