# Publisher object

Here are the fields in a publisher object. When you use the API to get a single publisher or lists of publishers, this is what's returned.

### `alternate_titles`

_List:_ A list of alternate titles for this publisher.

```json
alternate_titles: [
  "Elsevier",
  "elsevier.com",
  "Elsevier Science",
  "Uitg. Elsevier",
"السفیر",  
"السویر",  
"انتشارات الزویر",  
"لودویک السفیر",  
  "爱思唯尔"
]
```

### `cited_by_count`

_Integer:_ The number of citations to works that are linked to this publisher through journals or other sources.

For example, if a publisher publishes 27 journals and those 27 journals have 3,050 works, this number is the sum of the cited\_by\_count values for all of those 3,050 works.

```json
cited_by_count: 407508754
```

### `country_codes`

_List:_ The countries where the publisher is primarily located, as an [ISO two-letter country code](https://en.wikipedia.org/wiki/ISO\_3166-1\_alpha-2).

```json
country_codes: ["DE"]
```

### `counts_by_year`

_List:_ The values of [`works_count`](publisher-object.md#works\_count) and [`cited_by_count`](publisher-object.md#cited\_by\_count) for _each_ of the last ten years, binned by year. To put it another way: for every listed year, you can see how many new works are linked to this publisher, and how many times _any_ work linked to this publisher was cited.

Years with zero citations and zero works have been removed so you will need to add those back in if you need them.

```json
counts_by_year: [
    {
        year: 2021,
        works_count: 4211,
        cited_by_count: 120939
    },
    {
        year: 2020,
        works_count: 4363,
        cited_by_count: 119531
    },
    
    // and so forth
]
```

### `created_date`

_String:_ The date this `Publisher` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2017-08-08"
```

### `display_name`

_String:_ The primary name of the publisher.

```json
display_name: "Elsevier BV"
```

### `hierarchy_level`

_Integer:_ The hierarchy level for this publisher. A publisher with hierarchy level 0 has no parent publishers. A hierarchy level 1 publisher has one parent above it, and so on.

```json
hierarchy_level: 1
```

### `id`

_String:_ The OpenAlex ID for this publisher.

```json
id: "https://openalex.org/P4310320990"
```

### `ids`

_Object:_ All the external identifiers that we know about for this publisher. IDs are expressed as URIs whenever possible. Possible ID types:

* `openalex` _String:_ this publishers's [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id)
* `ror` _String:_ this publisher's ROR ID
* `wikidata` _String:_ this publisher's [Wikidata ID](https://www.wikidata.org/wiki/Wikidata:Identifiers)

<pre class="language-json"><code class="lang-json">ids: {
  openalex: "https://openalex.org/P4310320990",
  ror: "https://ror.org/02scfj030",
<strong>  wikidata: "https://www.wikidata.org/entity/Q746413"
</strong>},
</code></pre>

### `image_thumbnail_url`

_String:_ Same as [`image_url`](publisher-object.md#image\_url-1), but it's a smaller image.

This is usually a hotlink to a wikimedia image. You can change the `width=300` parameter in the URL if you want a different thumbnail size.

```json
image_thumbnail_url: "https://commons.wikimedia.org/w/index.php?title=Special:Redirect/file/MIT%20Press%20logo.svg&width=300"
```

### `image_url`

_String:_ URL where you can get an image representing this publisher. Usually this a hotlink to a Wikimedia image, and usually it's a seal or logo.

```json
image_url: "https://commons.wikimedia.org/w/index.php?title=Special:Redirect/file/MIT%20Press%20logo.svg"
```

### `lineage`

_List:_ [OpenAlex IDs](../../how-to-use-the-api/get-single-entities/#the-openalex-id) of publishers. The list will include this publisher's ID, as well as any parent publishers. If this publisher's `hierarchy_level` is 0, this list will only contain its own ID.

```json
id: "https://openalex.org/P4310321285",
...
hierarchy_level: 2,
lineage: [
    "https://openalex.org/P4310321285",
    "https://openalex.org/P4310319900",
    "https://openalex.org/P4310319965"
]
```

### `parent_publisher`

_String:_ An OpenAlex ID linking to the direct parent of the publisher. This will be null if the publisher's `hierarchy_level` is 0.

```json
parent_publisher: "https://openalex.org/P4310311775"
```

### `roles`

_List:_ List of role objects, which include the `role` (one of `institution`, `funder`, or `publisher`), the `id` ([OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id)), and the `works_count`.

In many cases, a single organization does not fit neatly into one role. For example, Yale University is a single organization that is a research university, funds research studies, and publishes an academic journal. The `roles` property links the OpenAlex entities together for a single organization, and includes counts for the works associated with each role.

The `roles` list of an entity ([Funder](../funders/), [Publisher](./), or [Institution](../institutions/)) always includes itself. In the case where an organization only has one role, the `roles` will be a list of length one, with itself as the only item.

```json
roles: [
    {
        role: "funder",
        id: "https://openalex.org/F4320308380",
        works_count: 1004,
    },
    {
        role: "publisher",
        id: "https://openalex.org/P4310315589",
        works_count: 13986,
    },
    {
        role: "institution",
        id: "https://openalex.org/I32971472",
        works_count: 250031,
    }
]
```

### `sources_api_url`

_String:_ An URL that will get you a list of all the sources published by this publisher.

We express this as an API URL (instead of just listing the sources themselves) because there might be thousands of sources linked to a publisher, and that's too many to fit here.

```json
sources_api_url: "https://api.openalex.org/sources?filter=host_organization.id:P4310319965"
```

### `summary_stats`

_Object:_ Citation metrics for this publisher

* `2yr_mean_citedness` _Float_: The 2-year mean citedness for this source. Also known as [impact factor](https://en.wikipedia.org/wiki/Impact\_factor). We use the year prior to the current year for the citations (the numerator) and the two years prior to that for the citation-receiving publications (the denominator).
* `h_index` _Integer_: The [_h_-index](https://en.wikipedia.org/wiki/H-index) for this publisher.
* `i10_index` _Integer_: The [i-10 index](https://en.wikipedia.org/wiki/Author-level\_metrics#i-10-index) for this publisher.

While the _h_-index and the i-10 index are normally author-level metrics and the 2-year mean citedness is normally a journal-level metric, they can be calculated for any set of papers, so we include them for publishers.

```json
summary_stats: {
    2yr_mean_citedness: 5.065784263815827,
    h_index: 985,
    i10_index: 176682
}
```

### `updated_date`

_String:_ The last time anything in this publisher object changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2021-12-25T14:04:30.578837"
```

### `works_count`

_Integer:_ The number of works published by this publisher.

```json
works_count: 13789818
```
