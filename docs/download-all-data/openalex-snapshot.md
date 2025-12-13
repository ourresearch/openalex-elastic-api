# OpenAlex snapshot

For most use cases, the REST API is your best option. However, you can also download ([instructions here](download-to-your-machine.md)) and install a complete copy of the OpenAlex database on your own server, using the database snapshot. The snapshot consists of seven files (split into smaller files for convenience), with one file for each of our seven entity types. The files are in the [JSON Lines](https://jsonlines.org/) format; each line is a JSON object, exactly the same as [you'd get from our API](../api-entities/works/get-a-single-work.md). The properties of these JSON objects are documented in each entity's object section (for example, the [`Work`](../api-entities/works/work-object/) object).

The snapshot is updated about once per month; you can read [release notes for each new update here.](https://github.com/ourresearch/openalex-guts/blob/main/files-for-datadumps/standard-format/RELEASE\_NOTES.txt)

If you've worked with a dataset like this before, the [snapshot data format](snapshot-data-format.md) may be all you need to get going. If not, read on.

The rest of this guide will tell you how to (a) download the snapshot and (b) upload it to your own database. We’ll cover two general approaches:

* Load the intact OpenAlex records to a data warehouse (we’ll use [BigQuery](https://cloud.google.com/bigquery) as an example) and use native JSON functions to query the [Work](../api-entities/works/work-object/), [Author](../api-entities/authors/author-object.md), [Source](../api-entities/sources/source-object.md), [Institution](../api-entities/institutions/institution-object.md), [Concept](../api-entities/concepts/concept-object.md), and [Publisher](../api-entities/publishers/publisher-object.md) objects directly.
* Flatten the records into a normalized schema in a relational database (we’ll use [PostgreSQL](https://www.postgresql.org/)) while preserving the relationships between objects.

We'll assume you're initializing a fresh snapshot. To keep it up to date, you'll have to take the information from [Downloading updated Entities](snapshot-data-format.md#downloading-updated-entities) and generalize from the steps in the guide.

{% hint style="warning" %}
This is hard. Working with such a big and complicated dataset hardly ever goes according to plan. If it gets scary, try the [REST API](../how-to-use-the-api/api-overview.md). In fact, try the REST API first. It can answer most of your questions and has a much lower barrier to entry.
{% endhint %}

There’s more than one way to do everything. We’ve tried to pick one reasonable default way to do each step, so if something doesn’t work in your environment or with the tools you have available, let us know.

Up next: the snapshot [data format](snapshot-data-format.md), [downloading the data](download-to-your-machine.md) and [getting it into your database](upload-to-your-database/).
