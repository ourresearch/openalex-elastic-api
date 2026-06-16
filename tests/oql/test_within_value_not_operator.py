"""`!` (the WoS / classic-OXURL within-value NOT) is rejected in OQL (#432).

`!` is Web of Science / classic-OpenAlex-URL syntax (`title_and_abstract.search:
England!"New England"`), NOT an OQL operator — OQL negates with a bare `not`
prefix (decision 23). The
classic `term!"phrase"` form is decomposed only on the OXURL→OQO surface (#431,
`url_parser.py`); typed into an OQL query it must raise a loud, fix-it error
rather than silently fold into a positive value (the original mis-parse, where
`England!"New England"` became one positive `England! New England` leaf).

The intent itself is expressed in OQL as `(England and not "New England")`
(corpus rows 130/131). See
oxjobs working/oql-systematic-reviews/work/NEGATION_PROBLEM_SPACE.md
"""
import pytest

from tests.oql.oql_v2 import parse, OQLError


def test_bang_quoted_phrase_is_rejected():
    """`A!"phrase"` is not OQL — raise OQL_BANG_NOT_SUPPORTED, don't mis-parse."""
    with pytest.raises(OQLError) as exc:
        parse('works where title/abstract has (England!"New England")')
    assert exc.value.code == "OQL_BANG_NOT_SUPPORTED"


def test_bang_bare_term_is_rejected():
    """`A!term` is rejected the same way."""
    with pytest.raises(OQLError) as exc:
        parse("works where title has (vaccine!mandatory)")
    assert exc.value.code == "OQL_BANG_NOT_SUPPORTED"


def test_leading_bang_is_rejected():
    """A leading `!` is rejected too (OQL has no `!`)."""
    with pytest.raises(OQLError) as exc:
        parse('works where title/abstract has (!"New England")')
    assert exc.value.code == "OQL_BANG_NOT_SUPPORTED"


def test_oql_not_form_still_works():
    """The OQL way to say it — a bare `not` prefix — is unaffected."""
    # parses without raising
    parse('works where title/abstract has (England and not "New England")')
