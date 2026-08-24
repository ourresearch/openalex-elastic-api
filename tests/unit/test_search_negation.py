"""oxjob #633 — `!` is the negation operator on search values, at BOTH doors.

Before this, `filter=display_name.search:!dog` and `search.title=!dog` both 400'd
("Search filters do not support the ! operator", Casey `e98d0ef` 2023-04-03 — a
fail-loudly guard, since nothing implemented it). Meanwhile OQL could express the query
(`works where title has (not dog)`) and the x_query echo rendered a `url` leg in exactly
the banned shape — so every negated search echoed a URL that 400'd. Jason's call
(2026-08-24) was to implement the operator rather than null out the URL.

Live-verified against prod ES the same day:
    all works                              321,958,325
    display_name.search:dog                    108,275
    display_name.search:!dog               321,850,050  = exact complement
    display_name.search:dog|cat                371,657
    display_name.search:!dog|cat           321,586,668  = NOT(dog OR cat)
    display_name.search.exact:cancer treatment 225,119
    display_name.search.exact:!cancer treatment 321,733,206
"""
import pytest

from core.exceptions import APIQueryParamsError
from core.fields import SearchField
from core.search import escape_undocumented_lucene
from core.shared_view import split_leading_negation


class TestSplitLeadingNegation:
    """The param door's peel step."""

    @pytest.mark.parametrize("value,expected", [
        ("!dog", (True, "dog")),
        ("!dog cat", (True, "dog cat")),
        ('!"New England"', (True, '"New England"')),
        ("!dog !cat", (True, "dog !cat")),      # only the LEADING bang is the operator
        ("dog", (False, "dog")),
        ("dog !cat", (False, "dog !cat")),      # mid-value bang is not negation
        ("", (False, "")),
        (None, (False, None)),
    ])
    def test_peels_only_a_leading_bang(self, value, expected):
        assert split_leading_negation(value) == expected

    @pytest.mark.parametrize("value", ["!", "!   "])
    def test_bare_bang_is_not_a_negation_of_nothing(self, value):
        # Negating an empty value would mean "everything"; leave it alone and let the
        # normal empty-value path handle it rather than silently matching the corpus.
        negated, remaining = split_leading_negation(value)
        assert negated is False
        assert remaining == value


class TestMidValueBangIsLiteral:
    """A `!` that is not the leading operator is text, not Lucene NOT.

    Before #633 the two engine branches disagreed: the plain analyzed branch dropped it
    as punctuation (`dog!cat` = `dog cat` = 3,230) while the boolean/phrase/wildcard
    branch handed it to ES query_string, where `!cat` is NOT. Escaping closes that split
    the same way `^ & { }` and leading `+`/`-` were closed in `5c61bb7`.
    """

    @pytest.mark.parametrize("value,expected", [
        ("dog !cat", "dog \\!cat"),
        ("dog AND !cat", "dog AND \\!cat"),
        ("a!b", "a\\!b"),
    ])
    def test_bang_is_escaped_outside_quotes(self, value, expected):
        assert escape_undocumented_lucene(value) == expected

    def test_bang_inside_quotes_is_left_alone(self):
        # Lucene already treats it literally inside a phrase.
        assert escape_undocumented_lucene('"dog !cat"') == '"dog !cat"'

    def test_already_escaped_bang_is_not_double_escaped(self):
        assert escape_undocumented_lucene("dog \\!cat") == "dog \\!cat"


class TestSearchFieldNoLongerRejectsBang:
    """The filter door's guard is gone; the leading `!` is stripped before it gets here."""

    def test_validate_accepts_a_value_containing_a_bang(self):
        f = SearchField(param="display_name.search")
        f.validate("dog !cat")  # must not raise

    def test_validate_still_rejects_a_bad_wildcard(self):
        # The wildcard checks that shared this method must survive its rewrite (#337).
        f = SearchField(param="display_name.search")
        with pytest.raises(APIQueryParamsError):
            f.validate("*dog")
