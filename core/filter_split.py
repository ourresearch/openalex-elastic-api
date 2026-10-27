"""Split a `filter=` string into its filters (oxjob #1883).

A comma outside double quotes separates two filters, except inside a search filter's
value (`title.search:` ...), where it is text, as in a pasted title, unless another
filter starts right after it: a separating comma is always followed by a filter key and
its colon (`,type:article`). With a space before the key (`title.search:foo, type:x`)
the rest reads as search text; 0 requests did that in a day of sampled proxy logs, while
~1% of comma titles hold ", Word:".

%2C can't mark a literal comma: clients that encode the whole value send every
separator as %2C too. Used by core/utils.py (the filter door) and
query_translation/url_parser.py (the OQL echo); mirrored at the edge in
openalex-api-proxy src/f1Validation.ts (splitFilterString).
"""
import re

# What follows a comma that separates two filters: a filter key, then its colon.
NEXT_FILTER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*:")


def split_filter_string(filter_string):
    """
    Split a filter string by commas, but respect quoted strings, and keep a comma
    inside a search filter's value unless a new filter starts right after it.

    Examples:
        'type:article,raw_affiliation_strings.search:"Dept of Chemistry, UCLA"'
        -> ['type:article', 'raw_affiliation_strings.search:"Dept of Chemistry, UCLA"']
        'title.search:Music and British Culture, 1785,type:book'
        -> ['title.search:Music and British Culture, 1785', 'type:book']
    """
    parts = []
    current = ""
    in_quotes = False

    for i, char in enumerate(filter_string):
        if char == '"':
            in_quotes = not in_quotes
            current += char
        elif char == "," and not in_quotes:
            colon = current.find(":")
            in_search_value = colon >= 0 and current.find("search", 0, colon) >= 0
            if in_search_value and not NEXT_FILTER_RE.match(filter_string, i + 1):
                current += char
                continue
            if current:
                parts.append(current)
            current = ""
        else:
            current += char

    if current:
        parts.append(current)

    return parts
