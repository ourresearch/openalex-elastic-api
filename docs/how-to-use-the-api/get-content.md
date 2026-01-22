---
description: Download PDFs and machine-readable XML for OpenAlex works
---

# Get content

OpenAlex provides downloadable full-text content for approximately 60 million works. This includes PDFs and GROBID-parsed XML (TEI format).

{% hint style="warning" %}
Content downloads cost **100 credits per file**. A free API key provides 100,000 credits/day, so you can download about 1,000 files per day. See [rate limits](rate-limits-and-authentication.md) for details.
{% endhint %}

## Content coverage

About 60 million works have downloadable content:

* **\~60M PDFs** — original PDF files
* **\~43M GROBID XML** — machine-readable structured text (TEI format)

You can find works with content using the [`has_content`](../api-entities/works/work-object/#has_content) filter:

* Works with PDFs: [`https://api.openalex.org/works?filter=has_content.pdf:true`](https://api.openalex.org/works?filter=has_content.pdf:true)
* Works with GROBID XML: [`https://api.openalex.org/works?filter=has_content.grobid_xml:true`](https://api.openalex.org/works?filter=has_content.grobid_xml:true)

## Downloading content for a single work

Get a time-limited download URL for a specific work:

### PDF

```
GET https://content.openalex.org/works/{work_id}.pdf?api_key=YOUR_KEY
```

Example: [`https://content.openalex.org/works/W2741809807.pdf`](https://content.openalex.org/works/W2741809807.pdf)

### GROBID XML

```
GET https://content.openalex.org/works/{work_id}.grobid-xml?api_key=YOUR_KEY
```

Example: [`https://content.openalex.org/works/W2741809807.grobid-xml`](https://content.openalex.org/works/W2741809807.grobid-xml)

The response is a `302 redirect` to a time-limited (5-minute) download URL. Follow the redirect to download the file.

**Response headers**:

* `Location`: The presigned download URL (valid for 5 minutes)
* `X-RateLimit-Credits-Used`: Credits consumed (100 for success, 1 for 404)

### Error responses

| Status | Meaning                                         |
| ------ | ----------------------------------------------- |
| 302    | Success — follow redirect to download           |
| 404    | Work exists but no content available (1 credit) |
| 404    | Work does not exist                             |
| 429    | Rate limit exceeded                             |

## Examples

### Example: Build a corpus for AI synthesis

Say you want to use an LLM to synthesize research on microplastics in drinking water. Here's how to collect the PDFs:

**Step 1: Find relevant works with PDFs**

```
GET https://api.openalex.org/works?filter=default.search:microplastics%20drinking%20water,has_content.pdf:true&select=id,title,content_url&api_key=YOUR_KEY
```

This returns \~800 works. Page through using `cursor=*` to collect all `content_url` values.

**Step 2: Download and convert to text**

```python
import requests
import subprocess

work_ids = ["W4388482763", "W4386073691", ...]  # from step 1

for work_id in work_ids:
    # Get signed URL (follows redirect automatically)
    r = requests.get(
        f"https://content.openalex.org/works/{work_id}.pdf",
        params={"api_key": "YOUR_KEY"},
        allow_redirects=True
    )

    # Save PDF
    with open(f"{work_id}.pdf", "wb") as f:
        f.write(r.content)

    # Convert to markdown (using marker, pdftotext, or similar)
    subprocess.run(["marker", f"{work_id}.pdf", "-o", f"{work_id}.md"])
```

Now you have a text corpus ready for RAG or LLM synthesis.

### Example: Download all 60 million PDFs

For large-scale downloads, you'll need an enterprise credit pack. [Contact us](mailto:steve@ourresearch.org) for pricing.

{% hint style="info" %}
OpenAlex data is free per the [POSI principles](https://opendataservices.coop/projects/posi/). Services like high-volume API access are not. This keeps OpenAlex sustainable.
{% endhint %}

Once you have credits, here's the approach:

**Step 1: Page through all works with PDFs**

```
GET https://api.openalex.org/works?filter=has_content.pdf:true&select=id,content_url&per_page=100&cursor=*&api_key=YOUR_KEY
```

Use `select=id,content_url` to minimize response size. Each page gives you 100 works.

**Step 2: Download in parallel**

```python
"""
Proof-of-concept bulk downloader.
TODO: You (or your agent) must add error handling, retries,
rate limiting, 404 handling, network timeouts, and resume logic.
"""
import requests
from concurrent.futures import ThreadPoolExecutor

API_KEY = "YOUR_KEY"
CONTENT_URL = "https://content.openalex.org"
API_URL = "https://api.openalex.org"

def download_pdf(work_id):
    # TODO: add retry logic, timeout handling, 404 handling
    r = requests.get(
        f"{CONTENT_URL}/works/{work_id}.pdf",
        params={"api_key": API_KEY},
        allow_redirects=True
    )
    with open(f"pdfs/{work_id}.pdf", "wb") as f:
        f.write(r.content)

def get_works_page(cursor):
    # TODO: add retry logic for API errors
    r = requests.get(
        f"{API_URL}/works",
        params={
            "filter": "has_content.pdf:true",
            "select": "id",
            "per_page": 100,
            "cursor": cursor,
            "api_key": API_KEY
        }
    )
    data = r.json()
    return data["results"], data["meta"].get("next_cursor")

# Main loop
cursor = "*"
with ThreadPoolExecutor(max_workers=50) as executor:
    while cursor:
        works, cursor = get_works_page(cursor)
        work_ids = [w["id"].split("/")[-1] for w in works]

        # Download 100 PDFs in parallel
        executor.map(download_pdf, work_ids)
```

**Performance**: At 100 downloads/second, you'll finish in about a week. We recommend staying under 100 requests/second for reliable performance.

## Using content\_url directly

Each work with content includes a `content_url` field that provides direct access to the content endpoint:

```json
{
  "id": "https://openalex.org/W2741809807",
  "content_url": "https://content.openalex.org/works/W2741809807",
  // ... other fields
}
```

Append `.pdf` or `.grobid-xml` to download specific formats.

{% hint style="info" %}
`content_url` is only available through the API, not in the [snapshot](../download-all-data/openalex-snapshot.md).
{% endhint %}

## What is GROBID XML?

[GROBID](https://github.com/kermitt2/grobid) is a machine learning library that extracts structured information from PDFs. The output is TEI-encoded XML containing:

* Full text with section structure
* References/citations
* Tables and figures (metadata)
* Author and affiliation information

This is useful for text mining, citation analysis, and building knowledge graphs.

## Credit costs

| Action                                     | Credits     |
| ------------------------------------------ | ----------- |
| Download PDF or GROBID XML (success)       | 100         |
| Query for unavailable content (404)        | 1           |
| List works with content (via `/works` API) | 10 per page |
