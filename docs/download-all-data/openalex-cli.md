# OpenAlex CLI

The OpenAlex CLI is our official command-line tool for downloading content from OpenAlex. It's the easiest way to build a local corpus of PDFs for text mining, machine learning, or research.

```bash
pip install openalex-official
```

{% hint style="info" %}
**Work in progress.** The CLI currently focuses on PDF/XML downloads. We're adding more features like CSV export and metadata queries. [Follow development on GitHub](https://github.com/ourresearch/openalex-official).
{% endhint %}

## Quick examples

**Download PDFs on a topic:**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./climate-papers \
  --filter "topics.id:T10325,has_content.pdf:true"
```

**Download by DOI:**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./my-papers \
  --ids "10.1038/nature12373,10.1126/science.1234567"
```

**Pipe in a list of work IDs:**

```bash
cat work_ids.txt | openalex download \
  --api-key YOUR_KEY \
  --output ./corpus \
  --stdin
```

**Download with full metadata (JSON sidecar files):**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./papers \
  --filter "publication_year:2024,type:article" \
  --with-full-metadata
```

## Why use the CLI?

Building a robust downloader is harder than it looks. The CLI handles:

- **Parallel downloads** — Up to 200 concurrent connections
- **Automatic checkpointing** — Resume interrupted downloads without re-downloading
- **Adaptive rate limiting** — Adjusts to API conditions automatically
- **DOI resolution** — Auto-detects DOIs and converts them to OpenAlex IDs
- **Progress tracking** — Real-time stats in your terminal

At full speed, you can download thousands of PDFs per hour.

## Credit costs

Downloads cost **100 credits each**. With a free API key (100K credits/day), you can download about 1,000 files per day.

Need more? [Contact us](mailto:steve@ourresearch.org) about enterprise credit packs for large-scale projects.

## Full documentation

For all options and advanced usage, see the [GitHub README](https://github.com/ourresearch/openalex-official).

```bash
openalex download --help
```

## What's next?

We're actively developing the CLI. Planned features include:

- CSV/JSON export of search results
- Metadata-only downloads (no PDFs)
- More entity types beyond works

Have a feature request? [Open an issue](https://github.com/ourresearch/openalex-official/issues).
