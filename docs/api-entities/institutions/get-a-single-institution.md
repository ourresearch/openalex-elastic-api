# Get a single institution

It's easy to get an institution from from the API with: `/institutions/<entity_id>`. Here's an example:

* Get the institution with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `I27837315`: \
  [https://api.openalex.org/institutions/I27837315](https://api.openalex.org/institutions/I27837315)

That will return an [`Institution`](institution-object.md) object, describing everything OpenAlex knows about the institution with that ID:

```json
{
    "id": "https://openalex.org/I27837315",
    "ror": "https://ror.org/00jmfr291",
    "display_name": "University of Michigan–Ann Arbor",
    "country_code": "US",
    "type": "education",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### External IDs

You can look up institutions using external IDs such as a [ROR ID](https://ror.org/):

* Get the institution with ROR ID `https://ror.org/00cvxb145`:\
  [https://api.openalex.org/institutions/ror:https://ror.org/00cvxb145](https://api.openalex.org/institutions/ror:https://ror.org/00cvxb145)

Available external IDs for institutions are:

<table><thead><tr><th width="388.6666666666667">External ID</th><th width="416">URN</th></tr></thead><tbody><tr><td>ROR</td><td><code>ror</code></td></tr><tr><td>Microsoft Academic Graph (MAG)</td><td><code>mag</code></td></tr><tr><td>Wikidata</td><td><code>wikidata</code></td></tr></tbody></table>

### Select fields

You can use `select` to limit the fields that are returned in an institution object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for an institution object\
  [https://api.openalex.org/institutions/I27837315?select=id,display\_name](https://api.openalex.org/institutions/I27837315?select=id,display\_name)
