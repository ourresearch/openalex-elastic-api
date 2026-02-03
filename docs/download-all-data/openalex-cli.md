# OpenAlex CLI

The OpenAlex CLI is our official command-line tool for downloading data from OpenAlex. It's the easiest way to build a local corpus of work metadata and full-text content (PDFs, TEI XML) for text mining, machine learning, or research.

```bash
pip install openalex-official
```

{% hint style="info" %}
**Work in progress.** The CLI currently focuses on work metadata and content downloads. We're adding more features like CSV export and queries for other entity types. [Follow development on GitHub](https://github.com/ourresearch/openalex-official).
{% endhint %}

## Quick examples

**Download metadata for works on a topic:**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./frogs \
  --filter "topics.id:T10325"
```

This saves a JSON file for each work with the complete metadata from OpenAlex.

**Download metadata + PDFs:**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./frogs \
  --filter "topics.id:T10325" \
  --content pdf
```

**Download metadata + PDFs + TEI XML:**

```bash
openalex download \
  --api-key YOUR_KEY \
  --output ./frogs \
  --filter "topics.id:T10325" \
  --content pdf,xml
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

## Output format

By default, metadata is saved as JSON files alongside any content:

```
output/
├── W2741809807.json     # metadata (always saved)
├── W2741809807.pdf      # content (if --content pdf)
├── W2741809807.tei.xml  # content (if --content xml)
└── W1234567890.json
```

## Why use the CLI?

Building a robust bulk downloader is harder than it looks. The CLI handles:

- **Metadata by default** — Every work gets a complete JSON file
- **Parallel downloads** — Up to 200 concurrent connections
- **Automatic checkpointing** — Resume interrupted downloads without re-downloading
- **Adaptive rate limiting** — Adjusts to API conditions automatically
- **DOI resolution** — Auto-detects DOIs and converts them to OpenAlex IDs
- **Progress tracking** — Real-time stats in your terminal

At full speed, you can download thousands of works per hour.

## Credit costs

- **Metadata downloads are free** — The singleton API doesn't cost credits
- **Content downloads cost 100 credits each** — PDFs and TEI XML

With a free API key (100K credits/day), you can download unlimited metadata and about 1,000 content files per day.

Need more content? [Contact us](mailto:steve@ourresearch.org) about enterprise credit packs for large-scale projects.

## Full documentation

For all options and advanced usage, see the [GitHub README](https://github.com/ourresearch/openalex-official).

```bash
openalex download --help
```

## What's next?

We're actively developing the CLI. Planned features include:

- CSV/JSON export of search results
- More entity types beyond works

Have a feature request? [Open an issue](https://github.com/ourresearch/openalex-official/issues).
