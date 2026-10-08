"""Yes/no flags in English, as input (oxjob #1555, Jason 2026-10-08: accept either form).

The canonical form is `<flag> is true|false` (#363, 4f1bdf0). Before June 2026 each flag
read as its own sentence (`it's open access`, `it doesn't have a DOI`); those phrasings
are accepted again as input, leniently: `it is` / `it's`, `isn't`, `doesn't` / `does not`,
`has no`, with or without `a` / `an` / `the` (so `it has DOI` reads too).
"""
from typing import List, Optional, Tuple

# column: (true phrase, false phrase), the June 2026 table (oxjob #363, before 4f1bdf0)
BOOL_PHRASES = {
    'open_access.is_oa': ("it's open access", "it's not open access"),
    'institutions.is_global_south': ("it's from the global south", "it's not from the global south"),
    'is_retracted': ("it's retracted", "it's not retracted"),
    'has_doi': ('it has a DOI', "it doesn't have a DOI"),
    'has_orcid': ('it has an ORCID', "it doesn't have an ORCID"),
    'open_access.any_repository_has_fulltext': ('it has fulltext in a repository', "it doesn't have fulltext in a repository"),
    'citation_normalized_percentile.is_in_top_1_percent': ("it's in the top 1% by citations", "it's not in the top 1% by citations"),
    'citation_normalized_percentile.is_in_top_10_percent': ("it's in the top 10% by citations", "it's not in the top 10% by citations"),
    'has_abstract': ('it has an abstract', "it doesn't have an abstract"),
    'has_references': ('it has references', "it doesn't have references"),
    'has_pmid': ("it's indexed by PubMed", "it's not indexed by PubMed"),
    'has_pmcid': ('it has a PMCID', "it doesn't have a PMCID"),
    'mag_only': ("it's indexed by MAG only", "it's not indexed by MAG only"),
    'is_xpac': ("it's in the extended index", "it's not in the extended index"),
    'is_paratext': ("it's paratext", "it's not paratext"),
    'has_content.pdf': ("it's linked to a PDF", "it's not linked to a PDF"),
    'best_oa_location.is_accepted': ("it's open access accepted", "it's not open access accepted"),
    'best_oa_location.is_published': ("it's open access published", "it's not open access published"),
    'has_fulltext': ('it has full text', "it doesn't have full text"),
    'primary_location.is_oa': ("it's open access in its primary location", "it's not open access in its primary location"),
    'primary_location.is_published': ("it's published in its primary location", "it's not published in its primary location"),
    'primary_location.is_accepted': ("it's accepted in its primary location", "it's not accepted in its primary location"),
    'primary_location.source.has_issn': ("it's in a primary source with an ISSN", "it's not in a primary source with an ISSN"),
    'primary_location.source.is_core': ("it's in a CWTS core source", "it's not in a CWTS core source"),
    'primary_location.source.is_in_doaj': ("it's indexed by DOAJ", "it's not indexed by DOAJ"),
    'primary_location.source.is_oa': ("it's in an OA source", "it's not in an OA source"),
    'best_oa_location.source.is_in_doaj': ("it's indexed by DOAJ in its best OA source", "it's not indexed by DOAJ in its best OA source"),
    'is_oa': ("it's fully open access", "it's not fully open access"),
    'is_in_doaj': ("it's in DOAJ", "it's not in DOAJ"),
    'locations.is_oa': ("it's open access in any location", "it's not open access in any location"),
    'locations.is_published': ("it's published in any location", "it's not published in any location"),
    'locations.is_accepted': ("it's accepted in any location", "it's not accepted in any location"),
    'locations.source.is_core': ("it's in a CWTS core source in any location", "it's not in a CWTS core source in any location"),
    'locations.source.is_in_doaj': ("it's indexed by DOAJ in any location", "it's not indexed by DOAJ in any location"),
    'has_oa_submitted_version': ('it has an OA submitted version', "it doesn't have an OA submitted version"),
}


_ARTICLES = {"a", "an", "the"}
_SPLIT = {"it's": ["it", "is"], "it’s": ["it", "is"], "its": ["it", "is"],
          "isn't": ["is", "not"], "isn’t": ["is", "not"],
          "doesn't": ["does", "not"], "doesn’t": ["does", "not"],
          "don't": ["does", "not"]}


def _norm(words: List[str]) -> List[Tuple[str, int]]:
    """Normalized words, each with the index of the input word it came from."""
    out: List[Tuple[str, int]] = []
    for i, w in enumerate(words):
        w = w.lower()
        for part in _SPLIT.get(w, [w]):
            if part in _ARTICLES:
                continue
            out.append((part, i))
    # `has no X` -> `does not have X`
    fixed: List[Tuple[str, int]] = []
    k = 0
    while k < len(out):
        if out[k][0] == "has" and k + 1 < len(out) and out[k + 1][0] == "no":
            fixed += [("does", out[k][1]), ("not", out[k][1]), ("have", out[k + 1][1])]
            k += 2
            continue
        fixed.append(out[k])
        k += 1
    return fixed


def _phrase_words(phrase: str) -> List[str]:
    return [w for w, _i in _norm(phrase.split())]


_PATTERNS = sorted(
    [(_phrase_words(p), col, val) for col, (pt, pf) in BOOL_PHRASES.items()
     for p, val in ((pt, True), (pf, False))],
    key=lambda x: -len(x[0]))


def match(words: List[str]) -> Optional[Tuple[str, bool, int]]:
    """(column, value, input words used) for the longest flag sentence that `words`
    starts with, or None. `words` are the input's next tokens, lowercased or not."""
    if not words or words[0].lower() not in ("it", "it's", "it’s", "its"):
        return None
    norm = _norm(words)
    seq = [w for w, _i in norm]
    for pat, col, val in _PATTERNS:
        if seq[:len(pat)] == pat:
            return col, val, norm[len(pat) - 1][1] + 1
    return None
