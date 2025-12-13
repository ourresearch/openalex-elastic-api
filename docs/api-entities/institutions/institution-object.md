# Institution object

These are the fields in an institution object. When you use the API to get a [single institution](get-a-single-institution.md) or [lists of institutions](get-lists-of-institutions.md), this is what's returned.

### `associated_institutions`

_List:_ `Institutions` related to this one. Each associated institution is represented as a [dehydrated Institution](institution-object.md#the-dehydratedinstitution-object) object, with one extra property:

* `relationship` (_String_): The type of relationship between this institution and the listed institution. Possible values: `parent`, `child`, and `related`.

Institution associations and the _relationship_ vocabulary come from [ROR's `relationships`](https://ror.readme.io/docs/ror-data-structure#relationships).

```json
associated_institutions: [
    {
        id: "https://openalex.org/I2802101240",
        ror: "https://ror.org/0483mr804",
        display_name: "Carolinas Medical Center",
        country_code: "US",
        type: "healthcare",
        relationship: "related"
    },
    {
        id: "https://openalex.org/I69048370",
        ror: "https://ror.org/01s91ey96",
        display_name: "Renaissance Computing Institute",
        country_code: "US",
        type: "education",
        relationship: "related"
    },
    
    // and so forth
]
```

### `cited_by_count`

_Integer:_ The total number [`Works`](../works/work-object/) that cite a work created by an author affiliated with this institution. Or less formally: the number of citations this institution has collected.

```json
cited_by_count: 21199844 
```

### `country_code`

_String:_ The country where this institution is located, represented as an [ISO two-letter country code](https://en.wikipedia.org/wiki/ISO\_3166-1\_alpha-2).

```json
country_code: "US"
```

### `counts_by_year`

_List:_ [`works_count`](institution-object.md#works\_count) and [`cited_by_count`](institution-object.md#cited\_by\_count) for each of the last ten years, binned by year. To put it another way: each year, you can see how many new works this institution put out, and how many times _any_ work affiliated with this institution got cited.

Years with zero citations and zero works have been removed so you will need to add those in if you need them.

```json
counts_by_year: [
    {
        year: 2022,
        works_count: 133,
        cited_by_count: 32731
    },
    {
        year: 2021,
        works_count: 12565,
        cited_by_count: 2180827
    },
    
    // and so forth
]
```

### `created_date`

_String:_ The date this `Institution` object was created in the OpenAlex dataset, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string.

```json
created_date: "2017-08-08"
```

### `display_name`

_String:_ The primary name of the institution.

```json
display_name: "University of North Carolina at Chapel Hill"
```

### `display_name_acronyms`

_List:_ Acronyms or initialisms that people sometimes use instead of the full [`display_name`](institution-object.md#display\_name).

```json
display_name_acronyms:["UNC"]
```

### `display_name_alternatives`

_List:_ Other names people may use for this institution.

```json
display_name_alternatives: [
    "UNC-Chapel Hill"
]
```

### `geo`

_Object:_ A bunch of stuff we know about the location of this institution:

* `city` (_String_): The city where this institution lives.
* `geonames_city_id` (_String_): The city where this institution lives, as a [GeoNames database](http://www.geonames.org/) ID.
* `region` (_String_): The sub-national region (state, province) where this institution lives.
* `country_code` (_String_): The country where this institution lives, represented as an [ISO two-letter country code](https://en.wikipedia.org/wiki/ISO\_3166-1\_alpha-2).
* `country` (_String_): The country where this institution lives.
* `latitude` (_Float_): Does what it says.
* `longitude` (_Float_): Does what it says.

```json
geo: {
    city: "Chapel Hill",
    geonames_city_id: "4460162",
    region: "North Carolina",
    country_code: "US",
    country: "United States",
    latitude: 35.9083,
    longitude: -79.0492
}
```

### `homepage_url`

_String:_ The URL for institution's primary homepage.

```json
homepage_url: "http://www.unc.edu/"
```

### `id`

_String:_ The [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id) for this institution.

```json
id: "https://openalex.org/I114027177"
```

### `ids`

_Object:_ All the external identifiers that we know about for this institution. IDs are expressed as URIs whenever possible. Possible ID types:

* `grid` (_String:_ this institution's [GRID](https://www.grid.ac/) [ID](https://en.wikipedia.org/wiki/RAS\_syndrome))
* `mag` (_Integer:_ this institution's [Microsoft Academic Graph](https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/) ID)
* `openalex` (_String:_ this institution's [OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id). Same as [`Institution.id`](institution-object.md#id))
* `ror` (_String:_ this institution's ROR ID. Same as [`Institution.ror`](institution-object.md#ror))
* `wikipedia` (_String:_ this institution's Wikipedia page URL)
* `wikidata` (_String:_ this institution's [Wikidata ID](https://www.wikidata.org/wiki/Wikidata:Identifiers))

{% hint style="info" %}
Many institution are missing one or more ID types (either because we don't know the ID, or because it was never assigned). Keys for null IDs are not displayed.
{% endhint %}

```json
ids: {
    openalex: "https://openalex.org/I114027177",
    ror: "https://ror.org/0130frc33",
    grid: "grid.10698.36",
    wikipedia: "https://en.wikipedia.org/wiki/University%20of%20North%20Carolina%20at%20Chapel%20Hill",
    wikidata: "https://www.wikidata.org/wiki/Q192334",
    mag: 114027177
}  
```

### `image_thumbnail_url`

_String:_ Same as [`image_url`](institution-object.md#image\_url-1), but it's a smaller image.

```json
image_thumbnail_url: "https://upload.wikimedia.org/wikipedia/en/thumb/5/5c/University_of_North_Carolina_at_Chapel_Hill_seal.svg/100px-University_of_North_Carolina_at_Chapel_Hill_seal.svg.png"
```

### `is_super_system`

_Boolean:_ True if this institution is a "super system". This includes large university systems such as the University of California System ([`https://openalex.org/I2803209242`](https://openalex.org/I2803209242)), as well as some governments and multinational companies.

We have this special flag for these institutions so that we can exclude them from other institutions' [`lineage`](#lineage), which we do because these super systems are not generally relevant in group-by results when you're looking at ranked lists of institutions.

The list of institution IDs marked as super systems can be found in [this file](https://github.com/ourresearch/openalex-guts/blob/main/const.py).

### `image_url`

_String:_ URL where you can get an image representing this institution. Usually this is hosted on Wikipedia, and usually it's a seal or logo.

```json
image_url: "https://upload.wikimedia.org/wikipedia/en/5/5c/University_of_North_Carolina_at_Chapel_Hill_seal.svg"
```

### `international`

_Object:_ The institution's display name in different languages. Derived from the wikipedia page for the institution in the given language.

* `display_name` (_Object_)
  * `key` (String): language code in [wikidata language code](https://www.wikidata.org/wiki/Property:P9753) format. Full list of languages is [here](https://doc.wikimedia.org/mediawiki-core/master/php/Names\_8php\_source.html).
  * `value` (String): `display_name` in the given language

```json
international: {
    display_name: {
        "ar": "جامعة نورث كارولينا في تشابل هيل",
        "en": "University of North Carolina at Chapel Hill",
        "es": "Universidad de Carolina del Norte en Chapel Hill",
        "zh-cn": "北卡罗来纳大学教堂山分校",
        ...
    }
}
```

### `lineage`

_List:_ [OpenAlex IDs](../../how-to-use-the-api/get-single-entities/#the-openalex-id) of institutions. The list will include this institution's ID, as well as any parent institutions. If this institution has no parent institutions, this list will only contain its own ID.

This information comes from [ROR's `relationships`](https://ror.readme.io/docs/ror-data-structure#relationships), specifically the Parent/Child relationships.

Super systems are excluded from the lineage. See [`is_super_system`](#is_super_system) above.

```json
id: "https://openalex.org/I170203145",
...
lineage: [
    "https://openalex.org/I170203145",
    "https://openalex.org/I90344618"
]
```

### `repositories`

_List:_ Repositories ([`Sources`](../sources/) with `type: repository`) that have this institution as their [`host_organization`](../sources/source-object.md#host\_organization)

```json
repositories: [
    {
        id: "https://openalex.org/S4306402521",
        display_name: "University of Minnesota Digital Conservancy (University of Minnesota)",
        host_organization: "https://openalex.org/I130238516",
        host_organization_name: "University of Minnesota",
        host_organization_lineage: ["https://openalex.org/I130238516"]
    }
    // and so forth
]
```

### `roles`

_List:_ List of role objects, which include the `role` (one of `institution`, `funder`, or `publisher`), the `id` ([OpenAlex ID](../../how-to-use-the-api/get-single-entities/#the-openalex-id)), and the `works_count`.

In many cases, a single organization does not fit neatly into one role. For example, Yale University is a single organization that is a research university, funds research studies, and publishes an academic journal. The `roles` property links the OpenAlex entities together for a single organization, and includes counts for the works associated with each role.

The `roles` list of an entity ([Funder](../funders/), [Publisher](../publishers/), or [Institution](./)) always includes itself. In the case where an organization only has one role, the `roles` will be a list of length one, with itself as the only item.

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

### `ror`

_String:_ The [ROR](https://ror.org/) ID for this institution. This is the [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for institutions.

The ROR (Research Organization Registry) identifier is a globally unique ID for research organization. [ROR is the successor to GRiD](https://www.digital-science.com/press-release/grid-passes-torch-to-ror/), which is no longer being updated.

```json
ror: "https://ror.org/0130frc33"
```

### `summary_stats`

_Object:_ Citation metrics for this institution

* `2yr_mean_citedness` _Float_: The 2-year mean citedness for this source. Also known as [impact factor](https://en.wikipedia.org/wiki/Impact\_factor). We use the year prior to the current year for the citations (the numerator) and the two years prior to that for the citation-receiving publications (the denominator).
* `h_index` _Integer_: The [_h_-index](https://en.wikipedia.org/wiki/H-index) for this institution.
* `i10_index` _Integer_: The [i-10 index](https://en.wikipedia.org/wiki/Author-level\_metrics#i-10-index) for this institution.

While the _h_-index and the i-10 index are normally author-level metrics and the 2-year mean citedness is normally a journal-level metric, they can be calculated for any set of papers, so we include them for institutions.

```json
summary_stats: {
    2yr_mean_citedness: 5.065784263815827,
    h_index: 985,
    i10_index: 176682
}
```

### `type`

_String:_ The institution's primary type, using the [ROR "type" controlled vocabulary](https://ror.readme.io/docs/ror-data-structure).

Possible values are: `Education`, `Healthcare`, `Company`, `Archive`, `Nonprofit`, `Government`, `Facility`, and `Other`.

```json
type: "education"
```

### `updated_date`

_String:_ The last time anything in this `Institution` changed, expressed as an [ISO 8601](https://en.wikipedia.org/wiki/ISO\_8601) date string. This date is updated for _any change at all_, including increases in various counts.

```json
updated_date: "2022-01-02T00:27:23.088909"
```

### `works_api_url`

_String:_ A URL that will get you a list of all the [`Works`](../works/work-object/) affiliated with this institution.

We express this as an API URL (instead of just listing the `Works` themselves) because most institutions have way too many works to reasonably fit into a single return object.

```json
works_api_url: "https://api.openalex.org/works?filter=institutions.id:I114027177"
```

### `works_count`

_Integer:_ The number of [`Works`](../works/work-object/) created by authors affiliated with this institution. Or less formally: the number of works coming out of this institution.

```json
works_count: 202704    
```

### `x_concepts`

{% hint style="danger" %}
`x_concepts` will be deprecated and removed soon. We will be replacing this functionality with [`Topics`](../topics/README.md) instead.
{% endhint %}

_List:_ The [`Concepts`](../concepts/concept-object.md) most frequently applied to works affiliated with this institution. Each is represented as a [dehydrated Concept](../concepts/concept-object.md#the-dehydratedconcept-object) object, with one additional attribute:

* `score` (_Float_): The strength of association between this institution and the listed concept, from 0-100.

```json
x_concepts: [
    {
        id: "https://openalex.org/C86803240",
        wikidata: null,
        display_name: "Biology",
        level: 0,
        score: 86.7
    },
    {
        id: "https://openalex.org/C185592680",
        wikidata: null,
        display_name: "Chemistry",
        level: 0,
        score: 51.4
    },
    
    // and so forth
]
```

## The `DehydratedInstitution` object

The `DehydratedInstitution` is a stripped-down [`Institution`](institution-object.md) object, with most of its properties removed to save weight. Its only remaining properties are:

* [`country_code`](institution-object.md#country\_code)
* [`display_name`](institution-object.md#display\_name)
* [`id`](institution-object.md#id)
* [`lineage`](institution-object.md#lineage)
* [`ror`](institution-object.md#ror)
* [`type`](institution-object.md#type)
