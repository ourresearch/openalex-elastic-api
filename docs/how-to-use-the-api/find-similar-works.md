---
description: Find semantically similar works using AI embeddings
---

# Find similar works

OpenAlex's standard [search](get-lists-of-entities/search-entities.md) uses keyword matching—it finds works containing the words you type. But sometimes you want to find works that are *about* the same thing, even if they use different terminology.

That's what `search.semantic` does. It uses AI embeddings to find semantically similar works based on meaning, not just keywords. Search for "machine learning applications in drug discovery" and you'll find relevant papers even if they say "AI-driven pharmaceutical research" or "computational approaches to medicine."

{% hint style="warning" %}
Semantic search requires an API key and costs **$0.001 per query**. See [rate limits](rate-limits-and-authentication.md) for details.
{% endhint %}

## How it works

When you submit a query:

1. We convert your text into a 1024-dimensional vector using an embedding model
2. We search our index of ~217 million work embeddings for the most similar vectors
3. We return the matching works, ranked by similarity score

The embedding model ([GTE-Large](https://huggingface.co/thenlper/gte-large)) captures semantic meaning, so conceptually related works cluster together in vector space even when they use different words.

## Basic usage

```
https://api.openalex.org/works?search.semantic=machine%20learning%20for%20drug%20discovery&api_key=YOUR_KEY
```

You can combine semantic search with any standard [filters](get-lists-of-entities/filter-entity-lists.md):

```
https://api.openalex.org/works?search.semantic=climate%20change%20adaptation&filter=publication_year:>2020,is_oa:true&api_key=YOUR_KEY
```

## Example: Literature review assistant

Say you're starting a literature review on CRISPR applications in agriculture. You could use keyword search, but you might miss papers that use terms like "genome editing," "gene modification," or "crop improvement" without mentioning "CRISPR" explicitly.

**Step 1: Find semantically related works**

```python
import requests

response = requests.get(
    "https://api.openalex.org/works",
    params={
        "search.semantic": "CRISPR gene editing applications in agriculture and crop improvement",
        "filter": "publication_year:>2020,is_oa:true",
        "api_key": "YOUR_KEY"
    }
)

results = response.json()["results"]
print(f"Found {len(results)} related works")
```

**Step 2: Explore the results**

```python
for work in results[:10]:
    print(f"{work['title'][:80]}")
```

You'll find works about plant genome modification, agricultural biotechnology, and crop science—even papers that never mention "CRISPR" directly but are highly relevant to your research.

## Limitations

{% hint style="info" %}
**English-focused**: The embedding model is optimized for English text. Non-English works are indexed, but similarity matching will be less accurate.
{% endhint %}

{% hint style="info" %}
**Abstracts required**: Only works with abstracts are indexed (~217 million works). Works without abstracts won't appear in results.
{% endhint %}

{% hint style="info" %}
**No datasets**: Dataset entities are not currently included in the vector index.
{% endhint %}

## When to use semantic search vs keyword search

| Use semantic search (`?search.semantic=`) when... | Use keyword search (`?search=`) when... |
|---------------------------------------------------|-----------------------------------------------|
| You want conceptually related works | You need exact term matches |
| You're exploring a new research area | You know the specific terminology |
| Your query is a sentence or paragraph | Your query is a few keywords |
| You want to find works using different terminology | You want to filter by many metadata fields |

## Costs

| Action | Cost |
|--------|------|
| Semantic search query | $0.001 |
