---
description: N-grams are groups of sequential words that occur in the text of a Work.
---

# Get N-grams

N-grams list the words and phrases that occur in the full text of a [`Work`](work-object/). We obtain them from Internet Archive's publicly (and generously :clap:) available [General Index](https://archive.org/details/GeneralIndex) and use them to enable fulltext searches on the Works that have them, through both the [`fulltext.search`](filter-works.md#fulltext.search) _filter_, and as an element of the more holistic [`search`](search-works.md#works-full-search) _parameter_.

Note that while n-grams are derived from the fulltext of a Work, the presence of n-grams for a given Work doesn't imply that the fulltext is available to you, the reader. It only means the fulltext was available to Internet Archive for indexing. [`Work.open_access`](work-object/#open\_access) is the place to go for information on public fulltext availability.

## API Endpoint

{% hint style="danger" %}
The n-gram API endpoint is not currently in service. The n-grams are still used on our backend to help power fulltext search. If you have any questions about this, please [submit a support ticket](https://openalex.org/feedback).
{% endhint %}

## Fulltext Coverage

You can see which works we have full-text for using the [`has_fulltext`](./work-object/README.md#has_fulltext) filter. This does not necessarily mean that the full text is available to you, dear reader; rather, it means that we have indexed the full text and can use it to help power [searches](../search-works.md). If you are trying to find the full text for yourself, try looking in [`open_access.oa_url`](./#open\_access).

We get access to the full text in one of two ways: either using an open-access PDF, or using [N-grams obtained from the Internet Archive](../get-n-grams.md). You can learn where a work's full text came from at [`fulltext_origin`](./#fulltext\_origin).

About 57 million works have n-grams coverage through [Internet Archive](https://archive.org/details/GeneralIndex). OurResearch is the first organization to host this data in a highly usable way, and we are proud to integrate it into OpenAlex!

Curious about n-grams used in search? [Browse them all](work-object/#ngrams\_url) via the API. Highly-cited works and less recent works are more likely to have n-grams, as shown by the coverage charts below:

<figure><img src="../../.gitbook/assets/OpenAlex works w_ cited count _ 50 and fulltext (percentage).svg" alt=""><figcaption></figcaption></figure>

<figure><img src="../../.gitbook/assets/OpenAlex total works w_ fulltext (percentage).svg" alt=""><figcaption></figcaption></figure>

<figure><img src="../../.gitbook/assets/OpenAlex total works w_ fulltext (count).svg" alt=""><figcaption></figcaption></figure>
