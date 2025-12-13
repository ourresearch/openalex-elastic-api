# Get a single topic

It's easy to get a topic from the API with: `/topics/<entity_id>`. Here's an example:

* Get the topic with the [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) `C71924100`:\
  [`https://api.openalex.org/topics/T11636`](https://api.openalex.org/topics/T11636)

That will return a [`Topic`](../topics/topic-object.md) object, describing everything OpenAlex knows about the topic with that ID:

```json
{
    "id": "https://openalex.org/T11636",
    "display_name": "Artificial Intelligence in Medicine",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### Select fields

You can use `select` to limit the fields that are returned in a topic object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a topic object\
  [`https://api.openalex.org/topics/T11636?select=id,display\_name`](https://api.openalex.org/topics/T11636?select=id,display\_name)
