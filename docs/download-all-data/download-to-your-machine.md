# Download to your machine

First off: anyone can get the data for free. While the files are hosted on [S3](https://aws.amazon.com/s3/) and we’ll be using Amazon tools in these instructions, you don’t need an Amazon account.

{% hint style="info" %}
Many thanks to the [AWS Open Data program](https://aws.amazon.com/opendata/). They cover the data-transfer fees (about $70 per download!) so users don't have to.
{% endhint %}

Before you load the snapshot contents to your database, you’ll need to get the files that make it up onto your own computer. There are exceptions, like [loading to redshift from s3](https://docs.aws.amazon.com/redshift/latest/dg/tutorial-loading-data.html) or using an ETL product like [Xplenty](https://xplenty.com) with an S3 connector. If either of these apply to you, see if the [snapshot data format](snapshot-data-format.md) is enough to get you started.

The easiest way to get the files is with the Amazon Web Services Command Line Interface (AWS CLI). Sample commands in this documentation will use the AWS CLI. You can find instructions for installing it on your system here: [https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

You can also browse the snapshot files using the AWS console here: [https://openalex.s3.amazonaws.com/browse.html](https://openalex.s3.amazonaws.com/browse.html). This browser and the CLI will work without an account.

This shell command will copy everything in the `openalex` S3 bucket to a local folder named `openalex-snapshot`. It'll take up roughly 300GB of disk space.

```bash
aws s3 sync "s3://openalex" "openalex-snapshot" --no-sign-request
```

{% hint style="warning" %}
If you download the snapshot into an existing folder, you'll need to use the [`aws s3 sync`](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html) `--delete` flag to remove files from any previous downloads. You can also remove the contents of destination folder manually. If you don't, you will see duplicate Entities that have moved from one file to another between snapshot updates.
{% endhint %}

The size of the snapshot will change over time. You can check the current size before downloading by looking at the output of:

```bash
aws s3 ls --summarize --human-readable --no-sign-request --recursive "s3://openalex/"
```

You should get a file structure like this (edited for length - there are more objects in the actual bucket):

```
openalex-snapshot/
├── LICENSE.txt
├── RELEASE_NOTES.txt
└── data
    ├── authors
    │   ├── manifest
    │   └── updated_date=2021-12-28
    │       ├── 0000_part_00.gz
    │       └── 0001_part_00.gz
    ├── concepts
    │   ├── manifest
    │   └── updated_date=2021-12-28
    │       ├── 0000_part_00.gz
    │       └── 0001_part_00.gz
    ├── institutions
    │   ├── manifest
    │   └── updated_date=2021-12-28
    │       ├── 0000_part_00.gz
    │       └── 0001_part_00.gz
    ├── sources
    │   ├── manifest
    │   └── updated_date=2021-12-28
    │       ├── 0000_part_00.gz
    │       └── 0001_part_00.gz
    └── works
        ├── manifest
        └── updated_date=2021-12-28
            ├── 0000_part_00.gz
            └── 0001_part_00.gz
```
