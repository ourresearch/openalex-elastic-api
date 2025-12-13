---
description: Topics assigned to works
---

# 💡 Topics

Works in OpenAlex are tagged with Topics using an automated system that takes into account the available information about the work, including title, abstract, source (journal) name, and citations. There are around 4,500 Topics. Works are assigned topics using a model that assigns scores for each topic for a work. The highest-scoring topic is that work's [`primary_topic`](../works/work-object/#primary_topic). We also provide additional highly ranked topics for works, in [Work.topics](../works/work-object/#topics).

To learn more about how OpenAlex topics work in general, see [the Topics page at OpenAlex help pages](https://help.openalex.org/hc/en-us/articles/24736129405719-Topics).

For a detailed description of the methods behind OpenAlex Topics, see our paper: ["OpenAlex: End-to-End Process for Topic Classification"](https://docs.google.com/document/d/1bDopkhuGieQ4F8gGNj7sEc8WSE8mvLZS/edit?usp=sharing\&ouid=106329373929967149989\&rtpof=true\&sd=true). The code and model are available at [`https://github.com/ourresearch/openalex-topic-classification`](https://github.com/ourresearch/openalex-topic-classification).

## What's next

Learn more about what you can do with topics:

* [The Topic object](topic-object.md)
* [Get a single topic](get-a-single-topic.md)
* [Get lists of topics](get-lists-of-topics.md)
* [Filter topics](filter-topics.md)
* [Search topics](search-topics.md)
* [Group topics](group-topics.md)
