---
description: Find semantically similar works using vector search
---

# Find similar works

OpenAlex's standard [search](get-lists-of-entities/search-entities.md) uses keyword matching—it finds works containing the words you type. But sometimes you want to find works that are *about* the same thing, even if they use different terminology.

That's what `/find/works` does. It uses AI embeddings to find semantically similar works based on meaning, not just keywords. Search for "machine learning applications in drug discovery" and you'll find relevant papers even if they say "AI-driven pharmaceutical research" or "computational approaches to medicine."

{% hint style="warning" %}
Semantic search requires an API key and costs **1,000 credits per query**. See [rate limits](rate-limits-and-authentication.md) for details.
{% endhint %}

## How it works

When you submit a query:

1. We convert your text into a 1024-dimensional vector using an embedding model
2. We search our index of ~217 million work embeddings for the most similar vectors
3. We return the matching works, ranked by similarity score

The embedding model ([GTE-Large](https://huggingface.co/thenlper/gte-large)) captures semantic meaning, so conceptually related works cluster together in vector space even when they use different words.

## Basic usage

### GET request

```
https://api.openalex.org/find/works?query=machine%20learning%20for%20drug%20discovery&api_key=YOUR_KEY
```

### POST request

For longer queries (up to 10,000 characters), use POST:

```bash
curl -X POST "https://api.openalex.org/find/works?api_key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "Your long query text here..."}'
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `query` | The text to find similar works for (required, max 10,000 chars) | — |
| `count` | Number of results to return (1-100) | 25 |
| `filter` | Metadata filters (see below) | — |

### Filters

You can narrow results using these filters:

| Filter | Example | Description |
|--------|---------|-------------|
| `publication_year` | `2023`, `>2020`, `2020-2023` | Filter by year |
| `is_oa` | `true`, `false` | Open access only |
| `has_abstract` | `true`, `false` | Has abstract |
| `has_content.pdf` | `true`, `false` | Has downloadable PDF |
| `has_content.grobid_xml` | `true`, `false` | Has parsed XML |

**GET with filters:**

```
https://api.openalex.org/find/works?query=climate%20change%20adaptation&filter=publication_year:>2020,is_oa:true&count=50&api_key=YOUR_KEY
```

**POST with filters:**

```bash
curl -X POST "https://api.openalex.org/find/works?api_key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "climate change adaptation strategies",
    "count": 50,
    "filter": {
      "publication_year": ">2020",
      "is_oa": true
    }
  }'
```

## Response format

```json
{
  "meta": {
    "count": 25,
    "query": "machine learning for drug discovery",
    "filters_applied": {"publication_year": ">2020"},
    "timing": {
      "embed_ms": 145,
      "search_ms": 89,
      "hydrate_ms": 156,
      "total_ms": 412
    }
  },
  "results": [
    {
      "score": 0.8934,
      "work": {
        "id": "https://openalex.org/W4385012847",
        "title": "Deep learning approaches for molecular property prediction",
        "publication_year": 2023,
        ...
      }
    },
    ...
  ]
}
```

Each result includes:
- `score`: Similarity score (0-1, higher is more similar)
- `work`: The full [work object](../api-entities/works/work-object/), same as you'd get from `/works/{id}`

## Example: Literature review assistant

Say you're starting a literature review on CRISPR applications in agriculture. You could use keyword search, but you might miss papers that use terms like "genome editing," "gene modification," or "crop improvement" without mentioning "CRISPR" explicitly.

**Step 1: Find semantically related works**

```python
import requests

response = requests.get(
    "https://api.openalex.org/find/works",
    params={
        "query": "CRISPR gene editing applications in agriculture and crop improvement",
        "filter": "publication_year:>2020,is_oa:true",
        "count": 100,
        "api_key": "YOUR_KEY"
    }
)

results = response.json()["results"]
print(f"Found {len(results)} related works")
```

**Step 2: Explore the results**

```python
for r in results[:10]:
    print(f"{r['score']:.3f} | {r['work']['title'][:80]}")
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

| Use semantic search (`/find/works`) when... | Use keyword search (`/works?search=`) when... |
|---------------------------------------------|-----------------------------------------------|
| You want conceptually related works | You need exact term matches |
| You're exploring a new research area | You know the specific terminology |
| Your query is a sentence or paragraph | Your query is a few keywords |
| You want to find works using different terminology | You want to filter by many metadata fields |

## Credit costs

| Action | Credits |
|--------|---------|
| Semantic search query | 1,000 |
