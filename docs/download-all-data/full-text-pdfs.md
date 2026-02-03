# Full-text PDFs

OpenAlex has cached copies of full-text content for about 60 million works:

* **60M PDFs** — Original PDF files
* **43M TEI XML** — Machine-readable structured text parsed by [Grobid](https://github.com/kermitt2/grobid)

This page covers bulk download options. For downloading individual files via the API, see [Download PDF content](../how-to-use-the-api/get-content.md).

## Storage details

The full-text archive is approximately **270 TB** total:

| Format | Files | Size |
|--------|-------|------|
| PDF | 60M | ~250 TB |
| TEI XML | 43M | ~20 TB |

## Download options

### Option 1: API (up to ~10K files)

Use the [content API](../how-to-use-the-api/get-content.md) to download files one at a time. Each download costs 100 credits.

With a free API key (100K credits/day), you can download about 1,000 files per day. Good for research projects, building small corpora, or sampling.

### Option 2: OpenAlex CLI (up to a few million files)

For larger downloads, use the [OpenAlex CLI](openalex-cli.md). It handles parallel downloads, automatic retries, checkpointing, and resume—so you don't have to build all that yourself.

**Install:**

```bash
pip install openalex-official
```

**Example: Download PDFs for a specific topic**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./climate-pdfs \
  --filter "topics.id:T10325,has_content.pdf:true" \
  --content pdf
```

**Example: Download 2026 works with Creative Commons licenses**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./cc-pdfs-2026 \
  --filter "publication_year:2026,best_oa_location.license:cc-by,has_content.pdf:true" \
  --content pdf
```

**Example: Download metadata + PDFs + TEI XML**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./my-corpus \
  --filter "topics.id:T10325,has_content.pdf:true" \
  --content pdf,xml
```

See the [OpenAlex CLI page](openalex-cli.md) for more examples and full documentation.

Standard credit rates apply (100 credits per content file download; metadata is free). At full speed, you can download a few million files in a few days.

### Option 3: Complete archive sync

For downloading the complete archive (all 60M files), we provide direct access to the storage bucket. You get time-limited credentials and use standard S3 tools to sync.

Files are stored on [Cloudflare R2](https://developers.cloudflare.com/r2/), which is fully compatible with the S3 API. You can use the AWS CLI, boto3, or any S3-compatible tool.

**One-time download:** 30-day R2 read access to sync the complete archive.

**Ongoing sync:** Persistent R2 read access is included with our enterprise subscription.

See the [pricing page](https://openalex.org/pricing) for details, or [contact us](mailto:steve@ourresearch.org) to get started.

**How it works:**

1. We generate R2 API credentials with read-only access
2. You sync using the AWS CLI:

```bash
aws s3 sync s3://openalex-pdfs ./pdfs \
  --endpoint-url https://a452eddbbe06eb7d02f4879cee70d29c.r2.cloudflarestorage.com
```

3. For ongoing sync, run periodically to get new files

At typical network speeds, expect 1-2 weeks to download the full archive.

## File naming

Files are named by UUID, not work ID:

```
openalex-pdfs/
├── 3a07228e-de2a-4c37-955d-b1411a498328.pdf
├── 7b12f4a1-8c9d-4e5f-a2b3-c4d5e6f7a8b9.pdf
└── ...

openalex-grobid-xml/
├── 3a07228e-de2a-4c37-955d-b1411a498328.xml.gz
├── 7b12f4a1-8c9d-4e5f-a2b3-c4d5e6f7a8b9.xml.gz
└── ...
```

To map work IDs to file UUIDs, use the [snapshot data](snapshot-data-format.md). The `locations` array in each work contains `pdf_url` fields that include the UUID.

## Licensing

The PDFs retain their original copyright. OpenAlex does not grant any additional rights to the content—we're just providing access to files we've collected.

To check the license for a specific work, use the [`best_oa_location.license`](../api-entities/works/work-object/#best_oa_location) field in the API. This tells you the license associated with the work's best open access location (e.g., `cc-by`, `cc-by-nc`, `cc0`, or `null` if unknown).

**Filter by license:**

You can use the API to find works with a specific license:

```
https://api.openalex.org/works?filter=has_content.pdf:true,best_oa_location.license:cc-by
```

This returns works that have downloadable PDFs and are licensed under [CC BY](https://creativecommons.org/licenses/by/4.0/).
