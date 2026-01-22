# Snapshot data format

Here are the details on where the OpenAlex data lives and how it's structured.

* All the data is stored in [Amazon S3](https://aws.amazon.com/s3/), in the [`openalex`](https://openalex.s3.amazonaws.com/browse.html) bucket.
* The data files are gzip-compressed [JSON Lines](https://jsonlines.org/), one row per entity.
* The bucket contains one prefix (folder) for each entity type: [work](https://openalex.s3.amazonaws.com/browse.html#data/works/), [author](https://openalex.s3.amazonaws.com/browse.html#data/authors/), [source](https://openalex.s3.amazonaws.com/browse.html#data/sources/), [institution](https://openalex.s3.amazonaws.com/browse.html#data/institutions/), [concept](https://openalex.s3.amazonaws.com/browse.html#data/concepts/), and [publisher](https://openalex.s3.amazonaws.com/browse.html#data/publishers/).
* Records are partitioned by [updated\_date](../api-entities/works/work-object/#updated\_date). Within each entity type prefix, each object (file) is further prefixed by this date. For example, if an [`Author`](../api-entities/authors/author-object.md) has an updated\_date of 2021-12-30 it will be prefixed`/data/authors/updated_date=2021-12-30/`.
  * If you're initializing a fresh snapshot, the `updated_date` partitions aren't important yet. You need all the entities, so for `Authors` you would get [`/data/authors`](https://openalex.s3.amazonaws.com/browse.html#data/authors/)`/*/*.gz`
* There are multiple objects under each `updated_date` partition. Each is under 2GB.
* The manifest file is JSON (in [redshift manifest](https://docs.aws.amazon.com/redshift/latest/dg/loading-data-files-using-manifest.html) format) and lists all the data files for each object type - [`/data/works/manifest`](https://openalex.s3.amazonaws.com/data/works/manifest) lists all the works.
* The gzip-compressed snapshot takes up about 330 GB and decompresses to about 1.6 TB.

The structure of each entity type is documented here: [Work](../api-entities/works/work-object/), [Author](../api-entities/authors/author-object.md), [Source](../api-entities/sources/source-object.md), [Institution](../api-entities/institutions/institution-object.md), [Concept](../api-entities/concepts/concept-object.md), and [Publisher](../api-entities/publishers/publisher-object.md).

{% hint style="info" %}
**API-only fields**: Some Work properties are only available through the API and not included in the snapshot:

* `content_url` — use the [content endpoint](../api-entities/works/get-content.md) directly with work IDs from the snapshot
{% endhint %}

{% hint style="info" %}
We have recently added folders for new entities `topics`, `fields`, `subfields`, and `domains`, and we will be adding others soon. This documentation will soon be updated to reflect these changes.
{% endhint %}

#### Visualization of the entity\_type/updated\_date folder structure

This is a screenshot showing the "leaf" nodes of one _entity type_, _updated date_ folder. You can also click around the browser links above to get a sense of the snapshot's structure.

![](<../.gitbook/assets/Screen Shot 2022-07-12 at 12.42.43 PM.png>)

### Downloading updated Entities

Once you have a copy of the snapshot, you'll probably want to keep it up to date. The `updated_date` partitions make this easy, but the way they work may be unfamiliar. Unlike a set of dated snapshots that each contain the full dataset as of a certain date, each partition contains the records that last changed on that date.

If we imagine launching OpenAlex on 2021-12-30 with 1000 `Authors`, each being newly created on that date, `/data/authors/` looks like this:

```
/data/authors/
├── manifest
└── updated_date=2021-12-30 [1000 Authors]
    ├── 0000_part_00.gz
    ...
    └── 0031_part_00.gz
```

If, on 2022-01-04, we made changes to 50 of those `Authors`, they would come _out of_ one of the files in `/data/authors/updated_date=2021-12-30` and go _into_ one in `/data/authors/updated_date=2022-01-04:`

```
/data/authors/
├── manifest
├── updated_date=2021-12-30 [950 Authors]
│   ├── 0000_part_00.gz
│   ...
│   └── 0031_part_00.gz
└── updated_date=2022-01-04 [50 Authors]
    ├── 0000_part_00.gz
    ...
    └── 0031_part_00.gz
```

If we also discovered 50 _new_ Authors, they would go in that same partition, so the totals would look like this:

```
/data/authors/
├── manifest
├── updated_date=2021-12-30 [950 Authors]
│   ├── 0000_part_00.gz
│   ...
│   └── 0031_part_00.gz
└── updated_date=2022-01-04 [100 Authors]
    ├── 0000_part_00.gz
    ...
    └── 0031_part_00.gz
```

So if you made your copy of the snapshot on 2021-12-30, you would only need to download `/data/authors/updated_date=2022-01-04` to get everything that was changed or added since then.

{% hint style="info" %}
To update a snapshot copy that you created or updated on date `X`, insert or update the records in objects where `updated_date` > `X`_._
{% endhint %}

You never need to go back for a partition you've already downloaded. Anything that changed isn't there anymore, it's in a new partition.

At the time of writing, these are the `Author` partitions and the number of records in each (in the actual dataset):

* `updated_date=2021-12-30/` - 62,573,099
* `updated_date=2022-12-31/` - 97,559,192
* `updated_date=2022-01-01/` - 46,766,699
* `updated_date=2022-01-02/` - 1,352,773

This reflects the creation of the dataset on 2021-12-30 and 145,678,664 combined updates and inserts since then - 1,352,773 of which were on 2022-01-02. Over time, the number of partitions will grow. If we make a change that affects all records, the partitions before the date of the change will disappear.

### Merged Entities

{% hint style="info" %}
See [Merged Entities](../how-to-use-the-api/get-single-entities/#merged-entity-ids) for an explanation of what Entity merging is and why we do it.
{% endhint %}

Alongside the folders for the six Entity types - work, author, source, institution, concept, and publisher - you'll find a seventh folder: [merged\_ids](https://openalex.s3.amazonaws.com/browse.html#data/merged\_ids/). Within this folder you'll find the IDs of Entities that have been merged away, along with the Entity IDs they were merged into.

Keep in mind that merging an Entity ID is a way of deleting the Entity while persisting its ID in OpenAlex. In practice, you can just delete the Entity it belongs to. It's not necessary to keep track of the date or which entity it was merged into.

Merge operations are separated into files by date. Each file lists the IDs of Entities that were merged on that date, and names the Entities they were merged into.

```
/data/merged_ids/
├── authors
│   └── 2022-06-07.csv.gz
├── institutions
│   └── 2022-06-01.csv.gz
├── venues
│   └── 2022-06-03.csv.gz
└── works
    └── 2022-06-06.csv.gz
```

For example, `data/merged_ids/authors/2022-06-07.csv.gz` begins:

```
merge_date,id,merge_into_id
2022-06-07,A2257618939,A2208157607
```

When processing this file, all you need to do is delete A2257618939. The effects of merging these authors, like crediting A2208157607 with their Works, are already reflected in the affected Entities.

Like the Entities' _updated\_date_ partitions, you only ever need to download merged\_ids files that are new to you. Any later merges will appear in new files with later dates.

### The `manifest` file

When we start writing a new `updated_date` partition for an entity, we'll delete that entity's `manifest` file. When we finish writing the partition, we'll recreate the manifest, including the newly-created objects. So if `manifest` is there, all the entities are there too.

The file is in [redshift manifest](https://docs.aws.amazon.com/redshift/latest/dg/loading-data-files-using-manifest.html) format. To use it as part of the update process for an Entity type (we'll keep using Authors as an example):

1. Download [`s3://openalex/data/authors/manifest`](https://openalex.s3.amazonaws.com/data/authors/manifest)`.`
2. Get the file list from the `url` property of each item in the `entries` list.
3. Download any objects with an `updated_date` you haven't seen before.
4. Download [`s3://openalex/data/authors/manifest`](https://openalex.s3.amazonaws.com/data/authors/manifest) again. If it hasn't changed since (1), no records moved around and any date partitions you downloaded are valid.
5. Decompress the files you downloaded and parse one JSON `Author` per line. Insert or update into your database of choice, using [each entity's ID](../how-to-use-the-api/get-single-entities/#the-openalex-id) as a primary key.

If you’ve worked with dataset like this before and have a toolchain picked out, this may be all you need to know. If you want more detailed steps, proceed to [download the data](download-to-your-machine.md).
