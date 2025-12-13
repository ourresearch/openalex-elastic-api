# Concepts

{% hint style="warning" %}
These are the original OpenAlex Concepts, which are being deprecated in favor of [Topics](../topics/README.md). We will continue to provide these Concepts for Works, but we will not be actively maintaining, updating, or providing support for these concepts. Unless you have a good reason to be relying on them, we encourage you to look into [Topics](../topics/README.md) instead.
{% endhint %}

Concepts are abstract ideas that works are about. OpenAlex indexes about 65k concepts.

* Get all the concepts used by OpenAlex:\
  [`https://api.openalex.org/concepts`](https://api.openalex.org/concepts)

The [Canonical External ID](../../how-to-use-the-api/get-single-entities/#canonical-external-ids) for OpenAlex concepts is the Wikidata ID, and each of our concepts has one, because all OpenAlex concepts are also Wikidata concepts.

Concepts are hierarchical, like a tree. There are 19 root-level concepts, and six layers of descendants branching out from them, containing about 65 thousand concepts all told. This concept tree is a modified version of [the one created by MAG](https://arxiv.org/abs/1805.12216).

You can view all the concepts and their position in the tree [as a spreadsheet here](https://docs.google.com/spreadsheets/d/1LBFHjPt4rj\_9r0t0TTAlT68NwOtNH8Z21lBMsJDMoZg/edit#gid=1473310811). About 85% of works are tagged with at least one concept (here's the [breakdown of concept counts per work](https://docs.google.com/spreadsheets/d/17DoJjyl1XVNZdVWs7fUy91z69U2tD8qtnBsaqJ-Zigo/edit#gid=0)).

## How concepts are assigned

Each work is tagged with multiple concepts, based on the title, abstract, and the title of its host venue. The tagging is done using an automated classifier that was trained on MAG’s corpus; you can read more about the development and operation of this classifier in [Automated concept tagging for OpenAlex, an open index of scholarly articles.](https://docs.google.com/document/d/1OgXSLriHO3Ekz0OYoaoP\_h0sPcuvV4EqX7VgLLblKe4/edit) You can implement the classifier yourself using [our models and code](https://github.com/ourresearch/openalex-concept-tagging).

A score is available for each [concept in a work](../works/work-object/#concepts), showing the classifier's confidence in choosing that concept. However, when assigning a lower-level child concept, we also assign all of its parent concepts all the way up to the root. This means that some concept assignment scores will be 0.0. The tagger adds concepts to works written in different languages, but it is optimized for English.

Concepts are linked to works via the [`concepts`](../works/work-object/#concepts) property, and to other concepts via the [`ancestors`](concept-object.md#ancestors) and [`related_concepts`](concept-object.md#related\_concepts) properties.

## What's next

Learn more about what you can do with concepts:

* [The Concept object](concept-object.md)
* [Get a single concept](get-a-single-concept.md)
* [Get lists of concepts](get-lists-of-concepts.md)
* [Filter concepts](filter-concepts.md)
* [Search concepts](search-concepts.md)
* [Group concepts](group-concepts.md)
