---
description: Are you an LLM? Start here.
---

# API Guide for LLMs

## OpenAlex API Guide for LLM Agents and AI Applications

OpenAlex is a fully open catalog of scholarly works, authors, sources, institutions, topics, publishers, and funders. Base URL: https://api.openalex.org Documentation: https://docs.openalex.org No authentication required | 100,000 credits/day limit (credit-based rate limiting)

### CRITICAL GOTCHAS - Read These First!

#### ❌ DON'T: Create ad-hoc sampling by using random page numbers

WRONG: ?page=5, ?page=17, ?page=42 to get "random" results This is NOT random sampling and will bias your results!

#### ✅ DO: Use the ?sample parameter for random sampling

CORRECT: https://api.openalex.org/works?sample=20 For consistent results, add a seed: ?sample=20\&seed=123

#### ❌ DON'T: Try to sample large datasets (10k+) in one request

The sample parameter maxes out at reasonable sizes for a single request.

#### ✅ DO: Use multiple samples with different seeds, then deduplicate

For large random samples (10k+ records):

1. Make multiple sample requests with different seeds
2. Combine results
3. Deduplicate by ID Example:

* ?sample=1000\&seed=1
* ?sample=1000\&seed=2
* ?sample=1000\&seed=3 Then deduplicate the combined results by checking work IDs. See: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/sample-entity-lists

#### ❌ DON'T: Search/filter by entity names directly

WRONG: /works?filter=author\_name:Einstein Entity names are ambiguous and this won't work!

#### ✅ DO: Use two-step lookup pattern for related entities

CORRECT two-step process:

1. Find the entity ID: /authors?search=einstein Response shows ID like "A5023888391" or full URI
2. Use ID to filter: /works?filter=authorships.author.id:A5023888391

Why? Names are ambiguous. "MIT" could be many institutions. IDs are unique. This applies to: authors, institutions, sources, topics, publishers, funders.

#### ❌ DON'T: Try to group by multiple dimensions in one query

WRONG: You cannot do SQL-style "GROUP BY topic, year" in a single API call.

#### ✅ DO: Make multiple queries and combine results client-side

To analyze by topic AND year (or any two dimensions):

1. Make one query per year: ?filter=publication\_year:2020\&group\_by=topics.id
2. Repeat for 2021, 2022, etc.
3. Combine results in your code The API only supports one group\_by per request.

#### ❌ DON'T: Ignore API errors or retry immediately on failure

API errors are common, especially at scale. Immediate retries can make things worse.

#### ✅ DO: Implement exponential backoff for retries

When you get errors (429 rate limit, 500 server error, timeouts):

1. Catch the error
2. Wait before retrying (1s, 2s, 4s, 8s, etc.)
3. Include a max retry limit (e.g., 5 attempts)
4. Log failures for debugging

#### ❌ DON'T: Use default page sizes for bulk extraction

Default is only 25 results per page. Slow for large extracts!

#### ✅ DO: Use maximum page size (200) for bulk data extraction

FAST: ?per-page=200 This reduces the number of API calls needed by 8x compared to default.

#### ❌ DON'T: Make sequential API calls for lists of known IDs

SLOW: Loop through 100 DOIs making 100 separate API calls.

#### ✅ DO: Use the OR filter (pipe |) for batch ID lookups

FAST: Combine up to 50 IDs in one query using pipe separator: /works?filter=doi:https://doi.org/10.1371/journal.pone.0266781|https://doi.org/10.1371/journal.pone.0267149|... You can include up to 50 values per filter. Use per-page=50 to get all results. See: https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/filter-entity-lists#addition-or

#### ❌ DON'T: Ignore rate limits when using concurrency/threading

Using multiple threads WITHOUT respecting rate limits will get you rate-limited or banned.

#### ✅ DO: Respect rate limits even across concurrent requests

* Default pool: 1 request/second
* Polite pool (with email): 10 requests/second
* Daily limit: 100,000 credits (list requests cost 10 credits, singleton requests cost 1) When using threading/async:

1. Implement rate limiting across ALL threads
2. Track requests per second globally
3. Add your email to requests for 10x higher limits

### Quick Reference

#### Base URL and Authentication

```
Base: https://api.openalex.org
Auth: None required
Rate: 100k credits/day (list=10cr, singleton=1cr)
```

#### Get Higher Rate Limits (Polite Pool)

Add your email to ANY parameter:

```
https://api.openalex.org/works?mailto=yourname@example.edu
```

This increases your rate limit from 1 req/sec → 10 req/sec Always do this for production applications!

#### Entity Endpoints

```
/works          - 240M+ scholarly documents (articles, books, datasets)
/authors        - Researcher profiles with disambiguated identities
/sources        - Journals, repositories, conferences
/institutions   - Universities, research organizations
/topics         - Subject classifications (3-level hierarchy)
/publishers     - Publishing organizations
/funders        - Funding agencies
/text           - Tag your own text with OpenAlex topics/keywords (POST)
```

#### Essential Query Parameters

```
filter=         - Filter results (see filter syntax below)
search=         - Full-text search across title/abstract/fulltext
sort=           - Sort results (e.g., cited_by_count:desc)
per-page=       - Results per page (default: 25, max: 200)
page=           - Page number for pagination
sample=         - Get random results (e.g., sample=50)
seed=           - Seed for reproducible sampling
select=         - Limit returned fields (e.g., select=id,title)
group_by=       - Aggregate results by a field
mailto=         - Your email (gets you into polite pool)
```

### Filter Syntax

#### Basic Filtering

```
Single filter:        ?filter=publication_year:2020
Multiple (AND):       ?filter=publication_year:2020,is_oa:true
Values (OR):          ?filter=type:journal-article|book
Negation:             ?filter=type:!journal-article
```

#### Comparison Operators

```
Greater than:         ?filter=cited_by_count:>100
Less than:            ?filter=publication_year:<2020
Range:                ?filter=publication_year:2020-2023
```

#### Multiple Values in Same Attribute

You can express AND within a single attribute two ways:

```
Repeat filter:        ?filter=institutions.country_code:us,institutions.country_code:gb
Use + symbol:         ?filter=institutions.country_code:us+gb
```

Both mean: "works with author from US AND author from GB"

#### OR Queries (Pipe Separator)

```
Any of these:         ?filter=institutions.country_code:us|gb|ca
Batch IDs:            ?filter=doi:10.1/abc|10.2/def|10.3/ghi
```

You can combine up to 50 values with pipes.

#### Important: OR only works WITHIN a filter, not BETWEEN filters

```
POSSIBLE:    ?filter=type:article|book (article OR book)
NOT POSSIBLE: Cannot do "(year=2020 OR year=2021) AND (type=article)"
WORKAROUND:  Make separate queries and combine results
```

### Common Patterns

#### Get Random Sample of Works

```
Small sample:
https://api.openalex.org/works?sample=20

Reproducible sample:
https://api.openalex.org/works?sample=20&seed=42

Large sample (10k+):
1. https://api.openalex.org/works?sample=1000&seed=1
2. https://api.openalex.org/works?sample=1000&seed=2
3. https://api.openalex.org/works?sample=1000&seed=3
...then deduplicate by ID
```

#### Search Works by Title/Abstract

```
Simple search:
https://api.openalex.org/works?search=machine+learning

Search specific field:
https://api.openalex.org/works?filter=title.search:CRISPR

Search + filter:
https://api.openalex.org/works?search=climate&filter=publication_year:2023
```

#### Find Works by Author (Two-Step Pattern)

```
Step 1 - Get author ID:
https://api.openalex.org/authors?search=Heather+Piwowar

Response includes: "id": "https://openalex.org/A5023888391"

Step 2 - Get their works:
https://api.openalex.org/works?filter=authorships.author.id:A5023888391

Alternative - Use ORCID directly:
https://api.openalex.org/works?filter=authorships.author.id:https://orcid.org/0000-0003-1613-5981
```

#### Find Works by Institution (Two-Step Pattern)

```
Step 1 - Get institution ID:
https://api.openalex.org/institutions?search=MIT

Response includes: "id": "https://openalex.org/I136199984"

Step 2 - Get their works:
https://api.openalex.org/works?filter=authorships.institutions.id:I136199984

Alternative - Use ROR directly:
https://api.openalex.org/works?filter=authorships.institutions.id:https://ror.org/042nb2s44
```

#### Get Highly Cited Recent Papers

```
https://api.openalex.org/works?filter=publication_year:>2020&sort=cited_by_count:desc&per-page=200
```

#### Get Open Access Works Only

```
All OA:
https://api.openalex.org/works?filter=is_oa:true

Gold OA only:
https://api.openalex.org/works?filter=open_access.oa_status:gold

Published OA version:
https://api.openalex.org/works?filter=has_oa_published_version:true
```

#### Filter by Multiple Criteria

```
Recent OA works about COVID from top institutions:
https://api.openalex.org/works?filter=publication_year:2022,is_oa:true,title.search:covid,authorships.institutions.id:I136199984|I27837315

Breaking down the filters:
- publication_year:2022 (recent)
- is_oa:true (open access)
- title.search:covid (about COVID)
- authorships.institutions.id:I136199984|I27837315 (MIT or Harvard)
```

#### Bulk Lookup by DOIs

```
Get specific works by DOI (efficient batch method):
https://api.openalex.org/works?filter=doi:https://doi.org/10.1371/journal.pone.0266781|https://doi.org/10.1371/journal.pone.0267149|https://doi.org/10.1371/journal.pone.0267890&per-page=50

Up to 50 DOIs per request. Use per-page=50 to ensure you get all results.
```

#### Get Works from Specific Journal

```
Step 1 - Get source ID:
https://api.openalex.org/sources?search=Nature

Response includes: "id": "https://openalex.org/S137773608"

Step 2 - Get works from that source:
https://api.openalex.org/works?filter=primary_location.source.id:S137773608
```

#### Aggregate/Group Data

```
Top topics by work count:
https://api.openalex.org/works?group_by=topics.id

Papers per year:
https://api.openalex.org/works?group_by=publication_year

Most prolific institutions:
https://api.openalex.org/works?group_by=authorships.institutions.id

Group with filters:
https://api.openalex.org/works?filter=publication_year:>2020&group_by=topics.id
```

#### Pagination for Large Result Sets

```
First page:
https://api.openalex.org/works?filter=publication_year:2023&per-page=200

Next pages:
https://api.openalex.org/works?filter=publication_year:2023&per-page=200&page=2
https://api.openalex.org/works?filter=publication_year:2023&per-page=200&page=3
...

The meta.count field tells you total results.
Calculate pages needed: ceil(meta.count / per-page)
```

#### Select Specific Fields Only (Faster Responses)

```
Just IDs and titles:
https://api.openalex.org/works?select=id,title&per-page=200

Multiple fields:
https://api.openalex.org/works?select=id,title,publication_year,cited_by_count
```

#### Autocomplete for Type-Ahead

```
Fast autocomplete endpoint for building search UIs:

Authors:
https://api.openalex.org/autocomplete/authors?q=einst

Institutions:
https://api.openalex.org/autocomplete/institutions?q=stanford

Works:
https://api.openalex.org/autocomplete/works?q=neural+networks

Typically returns in ~200ms
```

#### Tag Your Own Text (/text endpoint)

```
POST or GET to classify your own content:

https://api.openalex.org/text?title=Machine+learning+for+drug+discovery

Returns topics, keywords, and concepts for your text.
Costs 1000 credits per request (limited to 1 req/sec).
Text must be 20-2000 characters.
```

### Response Structure

#### List Endpoints

All list endpoints (/works, /authors, etc.) return:

```json
{
  "meta": {
    "count": 240523418,
    "db_response_time_ms": 42,
    "page": 1,
    "per_page": 25
  },
  "results": [
    { /* entity object */ },
    { /* entity object */ },
    ...
  ]
}
```

#### Single Entity Endpoints

Getting a single entity returns the object directly:

```
https://api.openalex.org/works/W2741809807
→ Returns a Work object directly (no meta/results wrapper)
```

#### Group By Responses

```json
{
  "meta": { "count": 100, ... },
  "group_by": [
    {
      "key": "https://openalex.org/T10001",
      "key_display_name": "Artificial Intelligence",
      "count": 15234
    },
    ...
  ]
}
```

### Performance Optimization Tips

#### 1. Use Maximum Page Size

```
SLOW:  Default 25 per page = more API calls
FAST:  ?per-page=200 (8x fewer API calls)
```

#### 2. Use Batch ID Lookups

```
SLOW:  Loop through 50 DOIs, 50 API calls
FAST:  One call with pipe-separated DOIs (up to 50)
```

#### 3. Select Only Fields You Need

```
SLOW:  Full objects with all fields
FAST:  ?select=id,title,publication_year
```

#### 4. Use Concurrent Requests with Rate Limiting

```python
# Pseudo-code
from concurrent.futures import ThreadPoolExecutor
import time

rate_limiter = RateLimiter(10)  # 10 req/sec with polite pool

def fetch_page(page_num):
    rate_limiter.wait()  # Ensure we don't exceed rate limit
    return requests.get(f"...&page={page_num}&mailto=you@example.edu")

with ThreadPoolExecutor(max_workers=10) as executor:
    results = executor.map(fetch_page, range(1, 101))
```

#### 5. Add Email for 10x Speed Boost

```
WITHOUT: 1 request/second max
WITH:    10 requests/second max

Just add: &mailto=yourname@example.edu
```

### Handling Errors

#### Common HTTP Status Codes

```
200 OK           - Success
400 Bad Request  - Invalid parameter (check your filter syntax)
403 Forbidden    - Rate limit exceeded (slow down, implement backoff)
404 Not Found    - Entity doesn't exist
500 Server Error - Temporary issue (retry with backoff)
```

#### Exponential Backoff Pattern

```python
def fetch_with_retry(url, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                # Rate limited
                wait_time = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                time.sleep(wait_time)
            elif response.status_code >= 500:
                # Server error
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                # Other error, don't retry
                response.raise_for_status()
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    raise Exception(f"Failed after {max_retries} retries")
```

### Entity-Specific Filter Examples

#### Works Filters (Most Common)

```
authorships.author.id           - Author's OpenAlex ID
authorships.institutions.id     - Institution's OpenAlex ID  
cited_by_count                  - Number of citations
is_oa                           - Is open access (true/false)
publication_year                - Year published
primary_location.source.id      - Source (journal) ID
topics.id                       - Topic ID
type                            - article, book, dataset, etc.
has_doi                         - Has a DOI (true/false)
has_fulltext                    - Has fulltext available (true/false)
```

#### Authors Filters

```
last_known_institution.id       - Current/last institution
works_count                     - Number of works authored
cited_by_count                  - Total citations
orcid                           - ORCID identifier
```

#### Sources Filters

```
host_organization               - Publisher/host
type                            - journal, repository, etc.
is_oa                           - Is open access
```

#### Institutions Filters

```
type                            - education, healthcare, company, etc.
country_code                    - Two-letter country code
continent                       - africa, asia, europe, etc.
```

### External ID Support

You can use external IDs directly in the API:

#### Works

```
DOI:       /works/https://doi.org/10.7717/peerj.4375
PMID:      /works/pmid:29844763
```

#### Authors

```
ORCID:     /authors/https://orcid.org/0000-0003-1613-5981
```

#### Institutions

```
ROR:       /institutions/https://ror.org/02y3ad647
```

#### Sources

```
ISSN:      /sources/issn:0028-0836
```

### Advanced Tips

#### Reproducible Random Samples

Always use a seed for reproducible sampling:

```
https://api.openalex.org/works?sample=100&seed=42
```

Same seed = same results every time.

#### Finding Related Works

```
Get cited works:
1. Get work: /works/W2741809807
2. Response includes: "referenced_works": [...]
3. Fetch those: /works?filter=openalex_id:W123|W456|W789

Get citing works:
1. Get work: /works/W2741809807  
2. Response includes: "cited_by_api_url"
3. Follow that URL
```

#### Filtering by Date Ranges

```
Exact year:       ?filter=publication_year:2020
After:            ?filter=publication_year:>2020
Before:           ?filter=publication_year:<2020
Range:            ?filter=publication_year:2018-2022
```

#### Complex Boolean Searches

The search parameter supports boolean operators:

```
AND:  ?search=climate+AND+change
OR:   ?search=climate+OR+weather  
NOT:  ?search=climate+NOT+politics
```

### Rate Limiting Best Practices

#### Without Email (Default Pool)

* 1 request per second
* 100,000 credits per day
* Sequential processing recommended

#### With Email (Polite Pool)

* 10 requests per second
* 100,000 credits per day
* Parallel processing viable
* **Always include your email for production use**

#### Credit Costs

* Singleton requests (e.g., `/works/W123`): 1 credit
* List requests (e.g., `/works?filter=...`): 10 credits
* Text/Aboutness requests: 1,000 credits

#### Concurrent Requests Strategy

```
1. Track requests per second globally (not per thread)
2. Use a semaphore or rate limiter across threads
3. Add delays between batches if needed
4. Monitor for 403 responses (rate limit exceeded)
5. Back off if you hit limits
```

#### Daily Limit Management

With 100k credits/day limit:

* Singleton requests: up to 100,000/day
* List requests: up to 10,000/day
* Plan accordingly for large jobs
* Consider OpenAlex Premium for higher limits

### Common Mistakes to Avoid

1. ❌ Using page numbers for sampling → ✅ Use ?sample=
2. ❌ Filtering by entity names → ✅ Get IDs first, then filter
3. ❌ Default page size → ✅ Use per-page=200
4. ❌ Sequential ID lookups → ✅ Batch with pipe (|) operator
5. ❌ No error handling → ✅ Implement retry with backoff
6. ❌ Ignoring rate limits in threads → ✅ Global rate limiting
7. ❌ Trying to group by multiple fields → ✅ Multiple queries + combine
8. ❌ Not including email → ✅ Add mailto= for 10x speed
9. ❌ Fetching all fields → ✅ Use select= for needed fields only
10. ❌ Assuming instant responses → ✅ Add timeouts (30s recommended)

### Need More Info?

* Full documentation: https://docs.openalex.org
* API Overview: https://docs.openalex.org/how-to-use-the-api/api-overview
* Entity schemas: https://docs.openalex.org/api-entities
* Help: https://openalex.org/help
* User group: https://groups.google.com/g/openalex-users

### For Premium Features

If you need:

* More than 100k credits/day
* Faster than daily snapshot updates
* Commercial support
* SLA guarantees

See: https://openalex.org/pricing

***

Last updated: 2025-10-13 Maintained for: LLM agents, AI applications, and automated tools
