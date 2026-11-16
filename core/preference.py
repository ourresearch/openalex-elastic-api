import hashlib


def _hash_preference(value):
    """Hash a preference value to a short, fixed-length key.

    Elasticsearch's `preference` only needs to be *stable per distinct
    query* — it pins a query to a consistent set of shards so identical
    searches get stable scoring/ordering and warm shard-query-cache hits.
    Its literal content is never inspected.

    elasticsearch-py sends `preference` as a URL query-string parameter on
    the `_search` request. When we used the raw user search string, a long
    query (~4 KB) pushed the app->ES HTTP request line past ES
    `http.max_initial_line_length` (4096 B) -> `too_long_http_line_exception`
    -> 500. Hashing keeps identical queries on identical shards while making
    the param a fixed length regardless of query size. A hex digest never
    starts with `_`, so ES reserved-prefix handling is no longer needed.
    """
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def clean_preference(preference):
    """Return a stable, fixed-length shard-routing key for `preference`.

    Falsy input is returned unchanged so callers do not set a `preference`
    param when there is no search.
    """
    if not preference:
        return preference
    return _hash_preference(preference)


def combine_preferences(search_strings):
    """Combine multiple search strings into a single preference key.

    Sorts strings for determinism, joins with '|', and hashes.
    """
    combined = "|".join(sorted(search_strings))
    return clean_preference(combined)


# The search filters whose value pins shard routing, so scores and tie-breaks repeat.
# Without it each page request may land on a different copy of a shard, whose BM25 statistics
# differ slightly, so works with near-equal scores swap places between pages: paging a
# title_and_abstract.search by relevance returned 316 rows with only 315 distinct works, one
# repeated and one never shown (ZD 4463, oxjob #1035, 15 Nov 2026). Every lexical search filter
# pins it now; semantic.search ranks by vector, not BM25, so it stays out.
PREFERENCE_SEARCH_FILTERS = (
    "abstract.search",
    "abstract.search.exact",
    "default.search",
    "default.search.exact",
    "display_name.search",
    "display_name.search.exact",
    "fulltext.search",
    "fulltext.search.exact",
    "keyword.search",
    "raw_affiliation_strings.search",
    "raw_affiliation_strings.search.exact",  # its honest name (oxjob #400)
    "raw_author_name.search",
    "text.search",
    "title.search",
    "title.search.exact",
    "title_abstract_keywords.search",
    "title_abstract_keywords.search.exact",
    "title_and_abstract.search",
    "title_and_abstract.search.exact",
)


def set_preference_for_filter_search(filter_params, s):
    preference = None
    for filter_param in filter_params:
        for key in filter_param:
            if key in PREFERENCE_SEARCH_FILTERS:
                preference = filter_param[key]
    if preference:
        s = s.params(preference=clean_preference(preference))
    return s
