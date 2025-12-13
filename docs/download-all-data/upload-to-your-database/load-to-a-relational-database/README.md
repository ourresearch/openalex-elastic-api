# Load to a relational database

Compared to using a data warehouse, loading the dataset into a relational database takes more work up front but lets you write simpler queries and run them on less powerful machines. One important caveat is that this is a _lot_ of data, and exploration will be very slow in most relational databases.

{% hint style="info" %}
By using a relational database, you trade flexibility for efficiency in certain selected operations. The tables, columns, and indexes we have chosen in this guide represent only one of many ways the entity objects could be stored. It may not be the best way to store them given the queries you want to run. Some queries will be fast, others will be painfully slow.
{% endhint %}

We’re going to use [PostgreSQL](https://www.postgresql.org/) as an example and skip the database server setup itself. We’ll assume you have a working postgres 13+ installation on which you can create schemas and tables and run queries. With that as a starting point, we'll take you through these steps:

1. Define the tables the data will be stored in and some key relationships between them (the "schema").
2. Convert the [JSON Lines](https://jsonlines.org/) files you [downloaded](../../download-to-your-machine.md) to [CSV](https://en.wikipedia.org/wiki/Comma-separated\_values) files that can be read by the database application. We'll flatten them to fit a [hierarchical database model](https://en.wikipedia.org/wiki/Hierarchical\_database\_model).
3. Load the CSV data into to the tables you created.
4. Run some queries on the data you loaded.

## Step 1: Create the schema

Running [this SQL](https://github.com/ourresearch/openalex-documentation-scripts/blob/main/openalex-pg-schema.sql) on your database (in the [psql](https://www.postgresql.org/docs/13/app-psql.html) client, for example) will initialize a schema for you.

Run it and you'll be set up to follow the next steps. To show you what it's doing, we'll explain some excerpts here, using the [concept](../../../api-entities/concepts/) entity as an example.

{% hint style="warning" %}
SQL in this section isn't anything additional you need to run. It's part of the schema we already defined in the file above.
{% endhint %}

The key thing we're doing is "flattening" the nested JSON data. Some parts of this are easy. [Concept.id](../../../api-entities/concepts/concept-object.md#id) is just a string, so it goes in a text column called "id":

```sql
CREATE TABLE openalex.concepts (
    id text NOT NULL,
    -- plus some other columns ...
);
```

But [Concept.related\_concepts](../../../api-entities/concepts/concept-object.md#related\_concepts) isn't so simple. You could store the JSON array intact in a postgres [JSON or JSONB](https://www.postgresql.org/docs/9.4/datatype-json.html) column, but you would lose much of the benefit of a relational database. It would be hard to answer questions about related concepts with more than one degree of separation, for example. So we make a separate table to hold these relationships:

```sql
CREATE TABLE openalex.concepts_related_concepts (
    concept_id text,
    related_concept_id text,
    score real
);
```

We can preserve `score` in this relationship table and look up any other attributes of the [dehydrated related concepts](../../../api-entities/concepts/concept-object.md#the-dehydratedconcept-object) in the main table `concepts`. Creating indexes on `concept_id` and `related_concept_id` lets us look up concepts on both sides of the relationship quickly.

## Step 2: Convert the JSON Lines files to CSV

[This python script](https://github.com/ourresearch/openalex-documentation-scripts/blob/main/flatten-openalex-jsonl.py) will turn the JSON Lines files you downloaded into CSV files that can be copied to the the tables you created in step 1.

{% hint style="warning" %}
This script assumes your downloaded snapshot is in `openalex-snapshot` and you've made a directory `csv-files` to hold the CSV files.

Edit `SNAPSHOT_DIR` and `CSV_DIR` at the top of the script to read or write the files somewhere else.
{% endhint %}

{% hint style="info" %}
This script has only been tested using python 3.9.5.
{% endhint %}

Copy the script to the directory above your snapshot (if the snapshot is in `/home/yourname/openalex/openalex-snapshot/`, name it something like `/home/yourname/openalex/flatten-openalex-jsonl.py)`

run it like this:

```bash
mkdir -p csv-files
python3 flatten-openalex-jsonl.py
```

{% hint style="info" %}
This script is slow. Exactly how slow depends on the machine you run it on, but think hours, not minutes.

If you're familiar with python, there are two big improvements you can make:

* Run [`flatten_authors`](https://github.com/ourresearch/openalex-documentation-scripts/blob/main/flatten-openalex-jsonl.py#L214) and [`flatten_works`](https://github.com/ourresearch/openalex-documentation-scripts/blob/main/flatten-openalex-jsonl.py#L544) at the same time, either by using threading in python or just running two copies of the script with the appropriate lines commented out.
* Flatten multiple `.gz` files within each entity type at the same time. This means parallelizing the `for jsonl_file_name ... loop` in each `flatten_` function and writing multiple CSV files per entity type.
{% endhint %}

You should now have a directory full of nice, flat CSV files:

```
$ tree csv-files/
csv-files/
├── concepts.csv
├── concepts_ancestors.csv
├── concepts_counts_by_year.csv
├── concepts_ids.csv
└── concepts_related_concepts.csv
...
$ cat csv-files/concepts_related_concepts.csv
concept_id,related_concept_id,score
https://openalex.org/C41008148,https://openalex.org/C33923547,253.92
https://openalex.org/C41008148,https://openalex.org/C119599485,153.019
https://openalex.org/C41008148,https://openalex.org/C121332964,143.935
...
```

## Step 3: Load the CSV files to the database

Now we run one postgres copy command to load each CSV file to its corresponding table. Each command looks like this:

```
\copy openalex.concepts_ancestors (concept_id, ancestor_id) from csv-files/concepts_ancestors.csv csv header
```

[This script](https://github.com/ourresearch/openalex-documentation-scripts/blob/main/copy-openalex-csv.sql) will run all the copy commands in the right order. Here's how to run it:

1. Copy it to the same place as the python script from step 2, right above the folder with your CSV files.
2. Set the environment variable OPENALEX\_SNAPSHOT\_DB to the [connection URI](https://www.postgresql.org/docs/13/libpq-connect.html#LIBPQ-CONNSTRING) for your database.
3. If your CSV files aren't in `csv-files`, replace each occurence of 'csv-files/' in the script with the correct path.
4. Run it like this (from your shell prompt)

```bash
psql $OPENALEX_SNAPSHOT_DB < copy-openalex-csv.sql
```

or like this (from psql)

```
\i copy-openalex-csv.sql
```

There are a bunch of ways you can do this - just run the copy commands from the script above in the right order in whatever client you're familiar with.

## Step 4: Run your queries!

Now you have all the OpenAlex data in your database and can run queries in your favorite client.

Here’s a simple one, getting the OpenAlex ID and OA status for each work:

```sql
select w.id, oa.oa_status
from openalex.works w 
join openalex.works_open_access oa 
on w.id = oa.work_id;
```

You'll get results like this (truncated, the actual result will be millions of rows):

| id                                                                   | oa\_status |
| -------------------------------------------------------------------- | ---------- |
| [https://openalex.org/W1496190310](https://openalex.org/W1496190310) | closed     |
| [https://openalex.org/W2741809807](https://openalex.org/W2741809807) | gold       |
| [https://openalex.org/W1496404095](https://openalex.org/W1496404095) | bronze     |

Here’s an example of a more complex query - finding the author with the most open access works of all time:

```sql
select 
    author_id, 
    count(distinct work_id) as num_oa_works 
from (
    select 
        a.id as author_id, 
        w.id as work_id, 
        oa.is_oa  
    from 
        openalex.authors a 
        join openalex.works_authorships wa on a.id = wa.author_id 
        join openalex.works w on wa.work_id = w.id 
        join openalex.works_open_access oa on w.id = oa.work_id
) work_authorships_oa 
where is_oa 
group by 1 
order by 2 desc 
limit 1;
```

We get the one row we asked for:

| author\_id                       | num\_oa\_works |
| -------------------------------- | -------------- |
| https://openalex.org/A2798520857 | 3297           |

Checking out [https://api.openalex.org/authors/A2798520857](https://api.openalex.org/authors/A2798520857), we see that this is Ashok Kumar at Manipal University Jaipur. We could also have found this directly in the query, through `openalex.authors`.
