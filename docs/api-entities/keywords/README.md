---
description: Short words or phrases assigned to works using AI
---

# 🗝️ Keywords

Works in OpenAlex are tagged with Keywords using an automated system based on Topics.

To learn more about how OpenAlex Keywords work in general, see [the Keywords page at OpenAlex help pages](https://help.openalex.org/how-it-works/keywords).

## Keyword object

These are the fields in a keyword object. When you use the API to get a [single keyword](#get-a-single-keyword) or [lists of keywords](#get-a-list-of-keywords), this is what's returned.

### `cited_by_count`

_Integer:_ The number of citations to works that have been tagged with this keyword. Or less formally: the number of citations to this keyword.

For example, if there are just two works tagged with this keyword and one of them has been cited 10 times, and the other has been cited 1 time, `cited_by_count` for this keyword would be `11`.

```json
cited_by_count: 4347000 
```

### `created_date`

_String:_ The date this `Keyword` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2024-04-10"
```

### `display_name`

_String:_ The English-language label of the keyword.

```json
display_name: "Cardiac Imaging"
```

### `id`

_String:_ The OpenAlex ID for this keyword.

```json
id: "https://openalex.org/keywords/cardiac-imaging"
```

### `updated_date`

_String:_ The last time anything in this keyword object changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2024-05-09T05:00:03.798420"
```

### `works_count`

_Integer:_ The number of works tagged with this keyword.

```json
works_count: 21737 
```

## Get a single keyword

It's easy to get a keyword from the API with: `/keyword/<entity_id>`. Here's an example:

* Get the keyword with the ID `cardiac-imaging`:\
  [`https://api.openalex.org/keywords/cardiac-imaging`](https://api.openalex.org/keywords/cardiac-imaging)

That will return a [`Keyword`](#keyword-object) object, describing everything OpenAlex knows about the keyword with that ID:

```json
{
    "id": "https://openalex.org/keywords/cardiac-imaging",
    "display_name": "Cardiac Imaging",
    // other fields removed for brevity
}
```

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

### Select fields

You can use `select` to limit the fields that are returned in a keyword object. More details are [here](../../how-to-use-the-api/get-lists-of-entities/select-fields.md).

* Display only the `id` and `display_name` for a keyword object\
  [`https://api.openalex.org/keywords/cardiac-imaging?select=id,display_name`](https://api.openalex.org/keywords/cardiac-imaging?select=id,display_name)


## Get a list of keywords

You can get lists of keywords:

* Get _all_ keywords in OpenAlex\
  [`https://api.openalex.org/keywords`](https://api.openalex.org/keywords)

Which returns a response like this:

```json
{
    "meta": {
        "count": 4516,
        "db_response_time_ms": 10,
        "page": 1,
        "per_page": 25,
        "groups_count": null
    },
    "results": [
        {
            "id": "https://openalex.org/T11475",
            "display_name": "Territorial Governance and Environmental Participation",
            // more fields (removed to save space)
        },
        {
            "id": "https://openalex.org/T13445",
            "display_name": "American Political Thought and History",
            // more fields (removed to save space)
        },
        // more results (removed to save space)
    ],
    "group_by": []
}
```

## Filter keywords

You can filter keywords with the `filter` parameter:

* Get keywords that are in the subfield "Epidemiology" (id: 2713)\
  [`https://api.openalex.org/keywords?filter=subfield.id:2713`](https://api.openalex.org/keywords?filter=subfield.id:2713)

{% hint style="info" %}
It's best to [read about filters](../../how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md) before trying these out. It will show you how to combine filters and build an AND, OR, or negation query
{% endhint %}

### `/keywords` attribute filters

You can filter using these attributes of the [`Keyword`](#keyword-object) object:

* [`cited_by_count`](#cited_by_count)
* [`id`](#id)
* [`works_count`](#works_count)

### `/keywords` convenience filters

These filters aren't attributes of the [`Keyword`](#keyword-object) object, but they're included to address some common use cases:

#### `default.search`

Value: a search string

This works the same as using the [`search` parameter](#search-keywords) for Keywords.

#### `display_name.search`

Value: a search string

Returns: keywords with a [`display_name`](#display_name) containing the given string.

* Get keywords with `display_name` containing "artificial" and "intelligence":\
  [`https://api.openalex.org/keywords?filter=display_name.search:artificial+intelligence`](https://api.openalex.org/keywords?filter=display_name.search:artificial+intelligence)

## Search keywords

You can search for keywords using the `search` query parameter, which searches the [`display_name`](#display_name) fileds. For example:

* Search keywords' `display_name` "artificial intelligence":\
  [https://api.openalex.org/keywords?search=artificial intelligence](https://api.openalex.org/keywords?search=artificial%20intelligence)

{% hint style="info" %}
You can read more about search [here](../../how-to-use-the-api/get-lists-of-entities/search-entities.md). It will show you how relevance score is calculated, how words are stemmed to improve search results, and how to do complex boolean searches.
{% endhint %}

## Group keywords

You can group keywords with the `group_by` parameter:

* Get counts of keywords by [`cited_by_count`](#cited_by_count):\
  [`https://api.openalex.org/keywords?group_by=cited_by_count`](https://api.openalex.org/keywords?group_by=cited_by_count)

Or you can group using one the attributes below.

{% hint style="info" %}
It's best to [read about group by](../../how-to-use-the-api/get-groups-of-entities.md) before trying these out. It will show you how results are formatted, the number of results returned, and how to sort results.
{% endhint %}

### Keywords group_by attributes

* [`cited_by_count`](#cited_by_count)
* [`works_count`](#works_count)
