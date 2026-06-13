"""Spec tests for the within-`.search`-value `!` NOT operator (zd#8101 WoS idiom).

Inside a field-scoped search value, `A!B` means "A AND NOT B" — the compact form
librarians paste verbatim from Web of Science / Scopus. It MUST desugar to the
same query as the explicit `(A and not(B))` form (charter decision 21's functional
`not()`):

  * `England!"New England"`  ==  `England and not("New England")`
        a quoted `!"phrase"` excludes the EXACT phrase (column → `.search.exact`).
  * `vaccine!mandatory`      ==  `vaccine and not(mandatory)`
        a bare `!term` excludes the stemmed term.

#432: was a silent mis-parse — the `!` got swallowed into one positive token
(`England! New England`), so the excluded phrase was positively REQUIRED. Fixed
in the search-value grammar. See
oxjobs working/oql-systematic-reviews/work/NEGATION_PROBLEM_SPACE.md
"""
from tests.oql.oql_v2 import parse
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(oql):
    return canonicalize_oqo(parse(oql)).to_dict()


def test_bang_quoted_phrase_excludes_exact():
    """`A!"phrase"` desugars to A AND NOT the exact phrase."""
    assert _canon('works where title/abstract contains (England!"New England")') == \
        _canon('works where title/abstract contains (England and not("New England"))')


def test_bang_bare_term_excludes_stemmed():
    """`A!term` desugars to A AND NOT the stemmed term."""
    assert _canon('works where title contains (vaccine!mandatory)') == \
        _canon('works where title contains (vaccine and not(mandatory))')
