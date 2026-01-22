---
description: Download PDFs and machine-readable XML for OpenAlex works
---

# Get content

OpenAlex includes links to publisher-hosted and repository-hosted full text for about 60 million [Open Access](../api-entities/works/work-object/#open\_access) works. But downloading from all those different sources can be inconvenient.

So we've cached copies of these files. We've got:

* **PDF** (60M): You can download PDFs directly from us.
* **XML** (43M): We've also parsed the PDFs (using [Grobid](https://github.com/kermitt2/grobid)) into [TEI XML](https://tei-c.org/), a format for representing the sections and semantics of scholarly papers.
* **Markdown**: coming soon.

{% hint style="warning" %}
Content downloads require an API key and cost **100 credits per file**. See [rate limits](rate-limits-and-authentication.md) for details.
{% endhint %}

## Getting content

### Get content for a single work

The URL pattern is simple:

```
https://content.openalex.org/works/{work_id}.pdf?api_key=YOUR_KEY
```

Replace `{work_id}` with any OpenAlex work ID (like `W2741809807`), and you'll download the PDF. Use `.grobid-xml` instead of `.pdf` to get the TEI XML version. If you don't specify an extension, it'll default to `.pdf`.

Examples:

* PDF: [`https://content.openalex.org/works/W2741809807.pdf?api_key=YOUR_KEY`](https://content.openalex.org/works/W2741809807.pdf?api_key=YOUR_KEY)
* TEI XML: [`https://content.openalex.org/works/W2741809807.grobid-xml?api_key=YOUR_KEY`](https://content.openalex.org/works/W2741809807.grobid-xml?api_key=YOUR_KEY)

### How it works

When you request content, here's what happens:

1. We check if we have the requested file. If not, you get a `404` and are charged just 1 credit.
2. If we have the file, we verify your API key has enough credits.
3. We generate a [presigned URL](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)—a temporary, authenticated link that grants access to the file on [Cloudflare R2](https://developers.cloudflare.com/r2/) where it's stored.
4. We return a `302 redirect` to that presigned URL. Your browser or HTTP client follows the redirect automatically.
5. Cloudflare verifies the signature and serves the file directly from their global edge network.

This approach is more scalable than streaming files through our servers. Since content is served directly from Cloudflare's edge infrastructure, downloads are fast regardless of where you are.

The presigned URL expires after 5 minutes. If you need to download the same file again, just hit the content endpoint again to get a fresh URL (but it will cost another 100 credits).

## Finding works with content

There are three ways to find works that have downloadable content:

### The YOLO method

Just plug a work ID into the URL template and see what happens. If we have it, great. If not, you'll get a 404 (and pay 1 credit for the lookup). Not recommended, but it works.

### Check the work object

If you already have a [work object](../api-entities/works/work-object/) from the API, look for the [`content_url`](../api-entities/works/work-object/#content\_url) field. If it's present, we have content available. Just append `.pdf` or `.grobid-xml` and add your API key:

```json
{
  "id": "https://openalex.org/W2741809807",
  "content_url": "https://content.openalex.org/works/W2741809807",
  ...
}
```

This is convenient when you're already working with work objects—no need to construct URLs yourself.

### Use the has\_content filter

This is the most powerful approach. Use the [`has_content`](../api-entities/works/filter-works.md#has\_content.pdf) filter to find works with downloadable content, combined with any other filters you want.

For example, find works about frogs that have PDFs:

```
https://api.openalex.org/works?filter=default.search:frogs,has_content.pdf:true
```

Or works with CC-BY licenses published since 2024:

```
https://api.openalex.org/works?filter=has_content.pdf:true,license.id:cc-by,publication_year:2024-
```

Then iterate through the results, grab each `content_url`, append `.pdf`, add your API key, and download. You can run 100 requests in parallel without any issues.

## Examples

### Example: Build a corpus for AI synthesis

Say you want to use an LLM to synthesize research on microplastics in drinking water. Here's how to collect the PDFs:

**Step 1: Find relevant works with PDFs**

```
GET https://api.openalex.org/works?filter=default.search:microplastics%20drinking%20water,has_content.pdf:true&select=id,title,content_url&per_page=100&api_key=YOUR_KEY
```

This returns \~800 works. Page through using `cursor=*` to collect all `content_url` values. We use `select=id,title,content_url` to minimize response size. We also use `per_page=100` to get 100 works per page, which means fewer API calls (faster and cheaper).

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

    # feed it to your LLM and synthesize the knowledge
    profit()
```

Now you have a text corpus ready for RAG or LLM synthesis. Vibe a query interface and you've got your own real-time semantic search engine with results synthesis.

### Example: Download millions of PDFs

Downloading millions of PDFs requires a lot of credits. You'll need a one-time credit pack—[contact us](mailto:steve@ourresearch.org) for pricing.

Once you have credits, here's the approach:

**Step 1: Page through all works with PDFs**

```
GET https://api.openalex.org/works?filter=has_content.pdf:true&select=id,content_url&per_page=100&cursor=*&api_key=YOUR_KEY
```

{% hint style="info" %}
Here's where you can limit your downloads to Creative Commons licensed works, certain topics, certain years--anything that our powerful filter syntax allows.
{% endhint %}

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

**Performance**: At 100 downloads/second, you can download all 60M PDFs in about 10 days. We recommend staying under 100 requests/second for reliable performance.

## Credit costs

| Action                                     | Credits     |
| ------------------------------------------ | ----------- |
| Download PDF or TEI XML (success)          | 100         |
| Query for unavailable content (404)        | 1           |
| List works with content (via `/works` API) | 10 per page |
