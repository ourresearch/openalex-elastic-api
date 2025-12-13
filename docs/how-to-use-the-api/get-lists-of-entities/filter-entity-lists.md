# Filter entity lists

Filters narrow the list down to just entities that meet a particular condition--specifically, a particular value for a particular attribute.

A list of filters are set using the `filter` parameter, formatted like this: `filter=attribute:value,attribute2:value2`. Examples:

* Get the works whose [type](../../api-entities/works/work-object/#type) is `book`:\
  [`https://api.openalex.org/works?filter=type:book`](https://api.openalex.org/works?filter=type:book)
* Get the authors whose name is Einstein:\
  [`https://api.openalex.org/authors?filter=display_name.search:einstein`](https://api.openalex.org/authors?filter=display\_name.search:einstein)

Filters are case-insensitive.

## Logical expressions

### Inequality

For numerical filters, use the less-than (`<`) and greater-than (`>`) symbols to filter by inequalities. Example:

* Get sources that host more than 1000 works:\
  [`https://api.openalex.org/sources?filter=works_count:>1000`](https://api.openalex.org/sources?filter=works\_count:%3E1000)

Some attributes have special filters that act as syntactic sugar around commonly-expressed inequalities: for example, the `from_publication_date` filter on `works`. See the endpoint-specific documentation below for more information. Example:

* Get all works published between 2022-01-01 and 2022-01-26 (inclusive):\
  [`https://api.openalex.org/works?filter=from_publication_date:2022-01-01,to_publication_date:2022-01-26`](https://api.openalex.org/works?filter=from\_publication\_date:2022-01-01,to\_publication\_date:2022-01-26)

### Negation (NOT)

You can negate any filter, numerical or otherwise, by prepending the exclamation mark symbol (`!`) to the filter value. Example:

* Get all institutions _except_ for ones located in the US:\
  [`https://api.openalex.org/institutions?filter=country_code:!us`](https://api.openalex.org/institutions?filter=country\_code:!us)

### Intersection (AND)

By default, the returned result set includes only records that satisfy _all_ the supplied filters. In other words, filters are combined as an AND query. Example:

* Get all works that have been cited more than once _and_ are free to read:\
  [`https://api.openalex.org/works?filter=cited_by_count:>1,is_oa:true`](https://api.openalex.org/works?filter=cited\_by\_count:%3E1,is\_oa:true)

To create an AND query within a single attribute, you can either repeat a filter, or use the plus symbol (`+`):

* Get all the works that have an author from France _and_ an author from the UK:
  * Using repeating filters: [`https://api.openalex.org/works?filter=institutions.country_code:fr,institutions.country_code:gb`](https://api.openalex.org/works?filter=institutions.country\_code:fr,institutions.country\_code:gb)
  * Using the plus symbol (`+`): [`https://api.openalex.org/works?filter=institutions.country_code:fr+gb`](https://api.openalex.org/works?filter=institutions.country\_code:fr+gb)

Note that the plus symbol (`+`) syntax will not work for search filters, boolean filters, or numeric filters.

### Addition (OR)

Use the pipe symbol (`|`) to input lists of values such that _any_ of the values can be satisfied--in other words, when you separate filter values with a pipe, they'll be combined as an `OR` query. Example:

* Get all the works that have an author from France or an author from the UK:\
  [`https://api.openalex.org/works?filter=institutions.country_code:fr|gb`](https://api.openalex.org/works?filter=institutions.country\_code:fr|gb)

This is particularly useful when you want to retrieve a many records by ID all at once. Instead of making a whole bunch of singleton calls in a loop, you can make one call, like this:

* Get the works with DOI `10.1371/journal.pone.0266781` _or_ with DOI `10.1371/journal.pone.0267149` (note the pipe separator between the two DOIs):\
  [`https://api.openalex.org/works?filter=doi:https://doi.org/10.1371/journal.pone.0266781|https://doi.org/10.1371/journal.pone.0267149`](https://api.openalex.org/works?filter=doi:https://doi.org/10.1371/journal.pone.0266781|https://doi.org/10.1371/journal.pone.0267149)

You can combine up to 100 values for a given filter in this way. You will also need to use the parameter `per-page=100` to get all of the results per query. See our [blog post](https://blog.ourresearch.org/fetch-multiple-dois-in-one-openalex-api-request/) for a tutorial.

{% hint style="danger" %}
You can use OR for values _within_ a given filter, but not _between_ different filters. So this, for example, **doesn't work and will return an error**:

* Get either French works _or_ ones published in the journal with ISSN 0957-1558:\
  [`https://api.openalex.org/works?filter=institutions.country_code:fr|primary_location.source.issn:0957-1558`](https://api.openalex.org/works?filter=institutions.country\_code:fr|primary\_location.source.issn:0957-1558)
{% endhint %}

## Available Filters

The filters for each entity can be found here:

* [Works](../../api-entities/works/filter-works.md)
* [Authors](../../api-entities/authors/filter-authors.md)
* [Sources](../../api-entities/sources/filter-sources.md)
* [Institutions](../../api-entities/institutions/filter-institutions.md)
* [Concepts](../../api-entities/concepts/filter-concepts.md)
* [Publishers](../../api-entities/publishers/filter-publishers.md)
* [Funders](../../api-entities/funders/filter-funders.md)
