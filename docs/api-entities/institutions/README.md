---
description: Universities and other organizations to which authors claim affiliations
---

# 🏫 Institutions

Institutions are universities and other organizations to which authors claim affiliations. OpenAlex indexes about 109,000 institutions.

* Get a list of OpenAlex institutions:\
  [`https://api.openalex.org/institutions`](https://api.openalex.org/institutions)

The [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for institutions is the ROR ID. All institutions in OpenAlex have ROR IDs.

Our information about institutions comes from metadata found in Crossref, PubMed, ROR, MAG, and publisher websites. In order to link institutions to works, we parse every affiliation listed by every author. These affiliation strings can be quite messy, so we’ve trained an algorithm to interpret them and extract the actual institutions with reasonably high reliability.

For a simple example: we will treat both “MIT, Boston, USA” and “Massachusetts Institute of Technology” as the same institution ([https://ror.org/042nb2s44](https://ror.org/042nb2s44)).

Institutions are linked to works via the [`works.authorships`](../works/work-object/#authorships) property.

Most papers use raw strings to enumerate author affiliations (eg "Univ. of Florida, Gainesville FL"). Parsing these determine the actual institution the author is talking about is nontrivial; you can find more information about how we do it, as well as downloading code, models, and test sets, [here on GitHub.](https://github.com/ourresearch/openalex-institution-parsing)

## What's next

Learn more about what you can do with institutions:

* [The Institution object](institution-object.md)
* [Get a single institution](get-a-single-institution.md)
* [Get lists of institutions](get-lists-of-institutions.md)
* [Filter institutions](filter-institutions.md)
* [Search institutions](search-institutions.md)
* [Group institutions](group-institutions.md)
