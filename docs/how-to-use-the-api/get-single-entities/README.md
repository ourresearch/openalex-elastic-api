---
description: Get a single entity, based on an ID
---

# Get single entities

This is a more detailed guide to single entities in OpenAlex. If you're just getting started, check out [get a single work](../../api-entities/works/get-a-single-work.md).

It's easy to get a singleton entity object from from the API:`/<entity_name>/<entity_id>.` Here's an example:

* Get the work with the [OpenAlex ID](./#the-openalex-id) `W2741809807`: [`https://api.openalex.org/works/W2741809807`](https://api.openalex.org/works/W2741809807)

That will return a [`Work`](../../api-entities/works/work-object/) object, describing everything OpenAlex knows about the work with that ID. You can use IDs other than OpenAlex IDs, and you can also format the IDs in different ways. Read below to learn more.

{% hint style="info" %}
You can make up to 50 of these queries at once by [requesting a list of entities and filtering on IDs using OR syntax](../get-lists-of-entities/filter-entity-lists.md#addition-or).
{% endhint %}

{% hint style="info" %}
To get a single entity, you need a single _unambiguous_ identifier, like an ORCID or an OpenAlex ID. If you've got an ambiguous identifier (like an author's name), you'll want to [search](../get-lists-of-entities/search-entities.md) instead.
{% endhint %}

## The OpenAlex ID

The OpenAlex ID is the primary key for all entities. It's a URL shaped like this: `https://openalex.org/<OpenAlex_key>`. Here's a real-world example:

[`https://openalex.org/W2741809807`](https://openalex.org/W2741809807)

### The OpenAlex Key

The OpenAlex ID has two parts. The first part is the Base; it's always `https://openalex.org/.` The second part is the Key; it's the unique primary key that identifies a given resource in our database.

The key starts with a letter; that letter tells you what kind of entity you've got: **W**(ork), **A**(uthor), **S**(ource), **I**(nstitution), **C**(oncept), **P**(ublisher), or **F**(under). The IDs are not case-sensitive, so `w2741809807` is just as valid as `W2741809807`. So in the example above, the Key is `W2741809807`, and the `W` at the front tells us that this is a `Work`.

Because OpenAlex was launched as a replacement for [Microsoft Academic Graph (MAG)](https://www.microsoft.com/en-us/research/project/microsoft-academic-graph/), OpenAlex IDs are designed to be backwards-compatible with MAG IDs, where they exist. To find the MAG ID, just take the first letter off the front of the unique part of the ID (so in the example above, the MAG ID is `2741809807`). Of course this won't yield anything useful for entities that don't have a MAG ID.

## Merged Entity IDs

At times we need to merge two Entities, effectively deleting one of them. This usually happens when we discover two Entities that represent the same real-world entity - for example, two [`Authors`](../../api-entities/authors/) that are really the same person.

If you request an Entity using its OpenAlex ID, and that Entity has been merged into another Entity, you will be redirected to the Entity it has been merged into. For example, https://openalex.org/A5092938886 has been merged into https://openalex.org/A5006060960, so in the API the former will redirect to the latter:

```bash
$ curl -i https://api.openalex.org/authors/A5092938886
HTTP/1.1 301 MOVED PERMANENTLY
Location: https://api.openalex.org/authors/A5006060960
```

Most clients will handle this transparently; you'll get the data for author A5006060960 without knowing the redirect even happened. If you have stored Entity ID lists and _do_ notice the redirect, you might as well replace the merged-away ID to skip the redirect next time.

## Supported IDs

For each entity type, you can retrieve the entity using by any of the external IDs we support--not just the native OpenAlex IDs. So for example:

* Get the work with this doi: `https://doi.org/10.7717/peerj.4375`:\
  [https://api.openalex.org/works/https://doi.org/10.7717/peerj.4375](https://api.openalex.org/works/https://doi.org/10.7717/peerj.4375)

This works with DOIs, ISSNs, ORCIDs, and lots of other IDs...in fact, you can use any ID listed in an entity's `ids` property, as listed below:

* [`Work.ids`](../../api-entities/works/work-object/#ids)
* [`Author.ids`](../../api-entities/authors/author-object.md#ids)
* [`Source.ids`](../../api-entities/sources/source-object.md#ids)
* [`Institution.ids`](../../api-entities/institutions/institution-object.md#ids)
* [`Concept.ids`](../../api-entities/concepts/concept-object.md#ids)
* [`Publisher.ids`](../../api-entities/publishers/publisher-object.md#ids)

## ID formats

Most of the external IDs OpenAlex supports are canonically expressed as URLs...for example, [the canonical form of a DOI](https://www.crossref.org/display-guidelines/) always starts with `https://doi.org/`. You can always use these URL-style IDs in the entity endpoints. Examples:

* Get the institution with the ROR [https://ror.org/02y3ad647](https://ror.org/02y3ad647) (University of Florida):\
  [`https://api.openalex.org/institutions/https://ror.org/02y3ad647`](https://api.openalex.org/institutions/https://ror.org/02y3ad647)
* Get the author with the ORCID [https://orcid.org/0000-0003-1613-5981](https://orcid.org/0000-0003-1613-5981) (Heather Piwowar):\
  [`https://api.openalex.org/authors/https://orcid.org/0000-0003-1613-5981`](https://api.openalex.org/authors/https://orcid.org/0000-0003-1613-5981)

For simplicity and clarity, you may also want to express those IDs in a simpler, URN-style format, and that's supported as well; you just write the namespace of the ID, followed by the ID itself. Here are the same examples from above, but in the namespace:id format:

* Get the institution with the ROR [https://ror.org/02y3ad647](https://ror.org/02y3ad647) (University of Florida):\
  [`https://api.openalex.org/institutions/ror:02y3ad647`](https://api.openalex.org/institutions/ror:02y3ad647)
* Get the author with the ORCID [https://orcid.org/0000-0003-1613-5981](https://orcid.org/0000-0003-1613-5981) (Heather Piwowar):\
  [`https://api.openalex.org/authors/orcid:0000-0003-1613-5981`](https://api.openalex.org/authors/orcid:0000-0003-1613-5981)

Finally, if you're using an OpenAlex ID, you can be even more succinct, and just use the [Key](./#the-openalex-key) part of the ID all by itself, the part that looks like `w1234567`:

* Get the work with OpenAlex ID https://openalex.org/W2741809807:\
  [https://api.openalex.org/works/W2741809807](https://api.openalex.org/works/W2741809807)

## Canonical External IDs

Every entity has an OpenAlex ID. Most entities also have IDs in other systems, too. There are hundreds of different ID systems, but we've selected a single external ID system for each entity to provide the **Canonical External ID**--this is the ID in the system that's been most fully adopted by the community, and is most frequently used in the wild. We support other external IDs as well, but the canonical ones get a privileged spot in the API and dataset.

These are the Canonical External IDs:

* Works: [DOI](../../api-entities/works/work-object/#title)
* Authors: [ORCID](../../api-entities/authors/author-object.md#orcid)
* Sources: [ISSN-L](../../api-entities/sources/source-object.md#issn\_l)
* Institutions: [ROR ID](../../api-entities/institutions/institution-object.md#ror)
* Concepts: [Wikidata ID](../../api-entities/concepts/concept-object.md#wikidata)
* Publishers: [Wikidata ID](../../api-entities/publishers/publisher-object.md#ids)

## Dehydrated entity objects

The full entity objects can get pretty unwieldy, especially when you're embedding a list of them in another object (for instance, a list of `Concept`s in a `Work`). For these cases, all the entities except `Work`s have a dehydrated version. This is a stripped-down representation of the entity that carries only its most essential properties. These properties are documented individually on their respective entity pages.

\\
