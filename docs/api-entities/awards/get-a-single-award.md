# Get a single award

It's easy to get an award from the API with: `/awards/<entity id>`. Here's an example:

* Get the award with the OpenAlex ID `G1929887790`:\
  [`https://api.openalex.org/awards/G1929887790`](https://api.openalex.org/awards/G1929887790)

That will return an [`Award`](award-object.md) object, describing everything OpenAlex knows about the award with that ID.

You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).

### External IDs

You can look up awards using external IDs such as DOI:

* Get the award with DOI `10.xxxx/award.123`:\
  [`https://api.openalex.org/awards/doi:10.xxxx/award.123`](https://api.openalex.org/awards/doi:10.xxxx/award.123)

### Select fields

You can use `select` to limit the fields that are returned in an award object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for an award:\
  [`https://api.openalex.org/awards/G1929887790?select=id,display_name`](https://api.openalex.org/awards/G1929887790?select=id,display_name)
