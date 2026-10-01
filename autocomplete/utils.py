import re

AUTOCOMPLETE_SOURCE = [
    "country_code",
    "id",
    "ids",
    "display_name",
    "authorships",
    "cited_by_count",
    "doi",
    "description",
    "geo",
    "host_organization_name",
    "issn_l",
    "last_known_institutions",
    "orcid",
    "observed_orcids",
    "publisher",
    "ror",
    "wikidata",
    "works_count",
]


# Query names on the keywords autocomplete clauses (oxjob #1464): a hit whose
# matched_queries holds ALTERNATIVE_MATCH but not NAME_MATCH appeared only through
# one of its display_name_alternatives, so its hint shows that alternative.
NAME_MATCH = "display_name"
ALTERNATIVE_MATCH = "display_name_alternatives"
KEYWORD_AUTOCOMPLETE_SOURCE = AUTOCOMPLETE_SOURCE + ["display_name_alternatives"]

_WORD = re.compile(r"\w+")


def _words(text):
    return _WORD.findall((text or "").casefold())


def matching_alternative(q, alternatives):
    """The alternative that q is a phrase prefix of, read the way
    match_phrase_prefix on the search_as_you_type field reads it: q's words appear
    together and in order, and its last word may be the start of a longer one
    ("heart att" -> "heart attack"). An alternative equal to q wins; otherwise the
    first match in list order. None when nothing matches.

    Done in Python rather than with ES highlighting because the unified
    highlighter returns nothing for a multi-word match_phrase_prefix on a
    search_as_you_type field (checked on topics-v4 `keywords.autocomplete`)."""
    q_words = _words(q)
    if not q_words:
        return None
    size = len(q_words)
    first = None
    for alternative in alternatives or []:
        words = _words(alternative)
        if words == q_words:
            return alternative
        if first is None and any(
            window[:-1] == q_words[:-1] and window[-1].startswith(q_words[-1])
            for window in (
                words[start:start + size]
                for start in range(len(words) - size + 1)
            )
        ):
            first = alternative
    return first


def is_cached_autocomplete(request):
    """Cache autocomplete with 1 or 2 characters."""
    if request.args.get("q") and len(request.args.get("q")) <= 2:
        cached = True
    else:
        cached = False
    return cached


def strip_punctuation(s):
    letters_to_replace = ".,!?"
    for letter in letters_to_replace:
        s = s.replace(letter, "")
    return s
