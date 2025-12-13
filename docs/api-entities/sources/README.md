---
description: Journals and repositories that host works
---

# 📚 Sources

Sources are where works are hosted. OpenAlex indexes about 249,000 sources. There are several types, including journals, conferences, preprint repositories, and institutional repositories.

* Get a list of OpenAlex sources:\
  [`https://api.openalex.org/sources`](https://api.openalex.org/sources)

The [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for sources is ISSN-L, which is a special "main" ISSN assigned to every sources (sources tend to have multiple ISSNs). About 90% of sources in OpenAlex have an ISSN-L or ISSN.

Our information about sources comes from Crossref, the ISSN Network, and MAG. These datasets are joined automatically where possible, but there’s also a lot of manual combining involved. We do not curate journals, so any journal that is available in the data sources should make its way into OpenAlex.

Several sources may host the same work. OpenAlex reports both the primary host source (generally wherever the [version of record](https://en.wikipedia.org/wiki/Version\_of\_record) lives), and alternate host sources (like preprint repositories).

Sources are linked to works via the [`works.primary_location`](../works/work-object/#primary\_location) and [`works.locations`](../works/work-object/#locations) properties.

{% hint style="info" %}
Check out the [Japanese Sources tutorial](https://github.com/ourresearch/openalex-api-tutorials/blob/main/notebooks/institutions/japan\_sources.ipynb), a Jupyter notebook showing how to use Python and the API to learn about all of the sources in a country.
{% endhint %}

## What's next

Learn more about what you can do with sources:

* [The Source object](source-object.md)
* [Get a single source](get-a-single-source.md)
* [Get lists of sources](get-lists-of-sources.md)
* [Filter sources](filter-sources.md)
* [Search sources](search-sources.md)
* [Group sources](group-sources.md)
