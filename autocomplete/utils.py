AUTOCOMPLETE_SOURCE = [
    "id",
    "display_name",
    "authorships",
    "cited_by_count",
    "doi",
    "description",
    "geo",
    "issn_l",
    "orcid",
    "publisher",
    "ror",
    "wikidata",
    "works_count",
]


def get_preference(q):
    """Elastic throws error if preference is set to _."""
    if q == "_":
        preference = "underscore"
    else:
        preference = q
    return preference


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
