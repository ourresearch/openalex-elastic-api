# Autocomplete entities

The autocomplete endpoint lets you add autocomplete or typeahead components to your applications, without the overhead of hosting your own API endpoint.

Each endpoint takes a string, and (very quickly) returns a list of entities that match that string.

Here's an example of an autocomplete component that lets users quickly select an institution:

![A user looking for information on the flagship of Florida's state university system.](https://i.imgur.com/f8yyWCd.png)

This is the query behind that result: [`https://api.openalex.org/autocomplete/institutions?q=flori`](https://api.openalex.org/autocomplete/institutions?q=flori)

The autocomplete endpoint is very fast; queries generally return in around 200ms. If you'd like to see it in action, we're using a slightly-modified version of this endpoint in the OpenAlex website here: [https://explore.openalex.org/](https://explore.openalex.org/)

## Request format

The format for requests is simple: `/autocomplete/<entity_type>?q=<query>`

* `entity_type` (optional): the name of one of the OpenAlex entities: `works`, `authors`, `sources`, `institutions`, `concepts`, `publishers`, or `funders`.
* `query`: the search string supplied by the user.

You can optionally [filter autocomplete results](autocomplete-entities.md#filter-autocomplete-results).

## Response format

Each request returns a response object with two properties:

* `meta`: an object with information about the request, including timing and results count
* `results`: a list of up to ten results for the query, sorted by citation count. Each result represents an entity that matched against the query.

```json
{
    meta: {
        count: 183,
        db_response_time_ms: 5,
        page: 1,
        per_page: 10
    },
    results: [
        {
            id: "https://openalex.org/I33213144",
            display_name: "University of Florida",
            hint: "Gainesville, USA",
            cited_by_count: 17190001,
            entity_type: "institution",
            external_id: "https://ror.org/02y3ad647"
        },
        // more results...
    ]
}
```

Each object in the `results` list includes these properties:

* `id` (string): The [OpenAlex ID](../get-single-entities/#the-openalex-id) for this result entity.
* `external_id` (string): The [Canonical External ID](../get-single-entities/#canonical-external-ids) for this result entity.
* `display_name` (string): The entity's `display_name` property.
* `entity_type` (string): The entity's type: `author`, `concept`, `institution`, `source`, `publisher`, `funder`, or `work`.
* `cited_by_count` (integer): The entity's `cited_by_count` property. For works this is simply the number of incoming citations. For other entities, it's the _sum_ of incoming citations for all the works linked to that entity.
* `works_count` (integer): The number of works associated with the entity. For entity type `work` it's always null.
* `hint`: Some extra information that can help identify the right item. Differs by entity type.

### The `hint` property

Result objects have a `hint` property. You can show this to users to help them identify which item they're selecting. This is particularly helpful when the `display_name` values of different results are the same, as often happens when autocompleting an author entity--a user who types in `John Smi` is going to see a lot of identical-looking results, even though each one is a different person.

The content of the `hint` property varies depending on what kind of entity you're looking up:

* `Work`: The work's authors' display names, concatenated. e.g. "R. Alexander Pyron, John J. Wiens"
* `Author`: The author's [last known institution](../../api-entities/authors/author-object.md#last\_known\_institution), e.g. "University of North Carolina at Chapel Hill, USA"
* `Source`: The `host_organization`, e.g. "Oxford University Press"
* `Institution`: The institution's location, e.g. "Gainesville, USA"
* `Concept`: The Concept's [description](../../api-entities/concepts/concept-object.md#description), e.g. "the study of relation between plant species and genera"

## IDs in autocomplete

[Canonical External IDs](../get-single-entities/#canonical-external-ids) and [OpenAlex IDs](../get-single-entities/#the-openalex-id) are detected within autocomplete queries and matched to the appropriate record if it exists. For example:

* The query [`https://api.openalex.org/autocomplete?q=https://orcid.org/0000-0002-7436-3176`](https://api.openalex.org/autocomplete?q=https://orcid.org/0000-0002-7436-3176) will search for the author with ORCID ID `https://orcid.org/0000-0002-7436-3176` and return 0 records if it does not exist.
* The query [`https://api.openalex.org/autocomplete/sources?q=S49861241`](https://api.openalex.org/autocomplete/sources?q=S49861241) will search for the source with OpenAlex ID `https://openalex.org/S49861241` and return 0 records if it does not exist.

## Filter autocomplete results

All entity [filters](filter-entity-lists.md) and [search](search-entities.md) queries can be added to autocomplete and work as expected, like:

[`https://api.openalex.org/autocomplete/works?filter=publication_year:2010&search=frogs&q=greenhou`](https://api.openalex.org/autocomplete/works?filter=publication\_year:2010\&search=frogs\&q=greenhou)
