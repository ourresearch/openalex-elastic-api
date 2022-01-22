# Changelog

* Update works endpoint to display new abstract inverted index data. [2021-01-22]
* Allow search queries to contain colons within the search string. [2021-01-16]
* Add support for phrase search with quotes: `works?filter=title.search:"type 1 diabetes control"` which ensures words 
follow each other in the exact order of the query.
* Remove support for bracketed or queries, like `concepts.id:[C15708023, C41008148]`. [2021-01-16] 
* Add `from_publication_date` and `to_publication_date` filter to works endpoint. Of note, `from_publication_date:2020-05-07` 
is greater than or equal to that date, while the filter `publication_date:>2020-05-07` is only greater than that date. The 
same differences applies for `to_publication_date` and `publication_date:<` filter. These new fields can be hyphenated. [2021-01-13]
* Add support for multiple terms OR filters, like `concepts.id:[C15708023, C41008148]`. [2021-01-12]
* Add support for numeric range filters, such as `cited_by_count:100-150`. [2021-01-12]
* Fix: Ensure sort params work properly when searching. [2021-01-11] 
* Boosted search results for every entity using cited by count. Documents with higher cited by count are more
likely to be shown first. [2021-01-11]
* Any query parameter or field can be written as hyphenated or underscore. 
So `group_by=publication_year` and `group-by=publication-year` will work the same. [2021-01-10]