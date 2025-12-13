# Get groups of entities

Sometimes instead of just listing entities, you want to _group them_ into facets, and count how many entities are in each group. For example, maybe you want to count the number of `Works` by [open access status](../api-entities/works/work-object/#open\_access). To do that, you call the entity endpoint, adding the `group_by` parameter. Example:

* Get counts of works by type:\
  [`https://api.openalex.org/works?group_by=type`](https://api.openalex.org/works?group\_by=type)

This returns a `meta` object with details about the query, and a `group_by` object with the groups you've asked for:

```json
{
    meta: {
        count: 246136992,
        db_response_time_ms: 271,
        page: 1,
        per_page: 200,
        groups_count: 15
    },
    group_by: [
        {
            key: "article",
            key_display_name: "article",
            count: 202814957
        },
        {
            key: "book-chapter",
            key_display_name: "book-chapter",
            count: 21250659
        },
        {
            key: "dissertation",
            key_display_name: "dissertation",
            count: 6055973
        },
        {
            key: "book",
            key_display_name: "book",
            count: 5400871
        },
        ...
    ]
}
```

So from this we can see that the majority of works (202,814,957 of them) are type `article`, with another 21,250,659 `book-chapter`, and so forth.

You can group by most of the same properties that you can [filter](get-lists-of-entities/filter-entity-lists.md) by, and you can combine grouping with filtering.

## Group properties

Each group object in the `group_by` list contains three properties:

#### `key`

Value: a string; the [OpenAlex ID](get-single-entities/#the-openalex-id) or raw value of the `group_by` parameter for members of this group. See details on [`key` and `key_display_name`](get-groups-of-entities.md#key-and-key\_display\_name).

#### `key_display_name`

Value: a string; the `display_name` or raw value of the `group_by` parameter for members of this group. See details on [`key` and `key_display_name`](get-groups-of-entities.md#key-and-key\_display\_name).

#### `count`

Value: an integer; the number of entities in the group.

## "Unknown" groups

The "unknown" group is hidden by default. If you want to include this group in the response, add `:include_unknown` after the group-by parameter.

* Group works by [`authorships.countries`](../api-entities/works/work-object/authorship-object.md#countries) (unknown group hidden):\
  [`https://api.openalex.org/works?group_by=authorships.countries`](https://api.openalex.org/works?group\_by=authorships.countries)
* Group works by [`authorships.countries`](../api-entities/works/work-object/authorship-object.md#countries) (includes unknown group):\
  [`https://api.openalex.org/works?group_by=authorships.countries:include_unknown`](https://api.openalex.org/works?group\_by=authorships.countries:include\_unknown)

## `key` and `key_display_name`

If the value being grouped by is an OpenAlex `Entity`, the [`key`](get-groups-of-entities.md#key) and [`key_display_name`](get-groups-of-entities.md#key\_display\_name) properties will be that `Entity`'s `id` and `display_name`, respectively.

* Group `Works` by `Institution`:\
  [`https://api.openalex.org/works?group_by=authorships.institutions.id`](https://api.openalex.org/works?group\_by=authorships.institutions.id)
* For one group, `key` is "[https://openalex.org/I136199984](https://openalex.org/I136199984)" and `key_display_name` is "Harvard University".

Otherwise, `key` is the same as `key_display_name`; both are the raw value of the `group_by` parameter for this group.

* Group `Concepts` by [`level`](../api-entities/concepts/concept-object.md#level):\
  [`https://api.openalex.org/concepts?group_by=level`](https://api.openalex.org/concepts?group\_by=level)
* For one group, both `key` and `key_display_name` are "3".

## Group-by `meta` properties

`meta.count` is the total number of works (this will be all works if no filter is applied). `meta.groups_count` is the count of groups (in the current page).

If there are no groups in the response, `meta.groups_count` is `null`.

Due to a technical limitation, we can only report the number of groups _in the current page,_ and not the total number of groups.

## Paging

The maximum number of groups returned is 200. If you want to get more than 200 groups, you can use cursor pagination. This works the same as it does when getting lists of entities, so [head over to the section on paging through lists of results](get-lists-of-entities/paging.md#cursor-paging) to learn how.

Due to technical constraints, when paging, results are sorted by key, rather than by count.
