---
description: People who create works
---

# 👩 Authors

Authors are people who create works. You can get an author from the API like this:

* Get a list of OpenAlex authors:\
  [`https://api.openalex.org/authors`](https://api.openalex.org/authors)

The [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for authors is ORCID; only a small percentage of authors have one, but the percentage is higher for more recent works.

Our information about authors comes from MAG, Crossref, PubMed, ORCID, and publisher websites, among other sources. To learn more about how we combine this information to get OpenAlex Authors, see [Author Disambiguation](https://help.openalex.org/hc/en-us/articles/24347048891543-Author-disambiguation).

Authors are linked to works via the [`works.authorships`](../works/work-object/#authorships) property.

## What's next

Learn more about what you can with authors:

* [The Author object](author-object.md)
* [Get a single author](get-a-single-author.md)
* [Get lists of authors](get-lists-of-authors.md)
* [Filter authors](filter-authors.md)
* [Search authors](search-authors.md)
* [Group authors](group-authors.md)
