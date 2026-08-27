"""oxjob #633 item 1 — the empty OR-operand bug + the param-door `|` lift.

Before this, an EMPTY OR-operand in a filter-door search value matched the
whole index: `filter=display_name.search:nature|` returned all 255,732 sources
(vs 222 for `nature`), because the empty operand built
SearchOpenAlex(search_terms="") -> match_all(). One stray keystroke silently
turned a scoped query into the whole corpus — the same silent-mis-scope class
as the 2026-07-18 whole-corpus export bug this job was created over.
Prod-verified 2026-08-24 (v2019):

    /works?filter=title_and_abstract.search.exact:cancer|   321,958,325 = all works
    /sources?filter=display_name.search:nature|                 255,732 = all sources
    /authors?filter=display_name.search:smith|              125,781,210 = all authors

Jason's call (2026-08-24): fail loudly (400), mirroring the whole-value empty
check in core/utils.py:map_filter_params.

The `|` ban on the PARAM door (`?search.title=dog|cat` -> 400) existed only to
stop that bug spreading to a second door, so it is lifted in the same change:
the param door now composes OR (and `!a|b` whole-list negation) exactly like
the filter door, in core/shared_view.py:build_search_value_query.
"""
import pytest
from elasticsearch_dsl import Search
from werkzeug.datastructures import MultiDict

from core.exceptions import APIQueryParamsError
from core.fields import SearchField, TermField
from core.filter import handle_or_query
from core.search import full_search_query, full_search_query_exact, scoped_search_query
from core.shared_view import _negate, build_search_value_query
from core.validate import validate_search_param


class FakeRequest:
    """Minimal request-like object (same shape as test_combined_search.py)."""

    def __init__(self, args_dict):
        self.args = MultiDict(args_dict)
        self.url = "http://test/works?" + "&".join(
            f"{k}={v}" for k, v in self.args.items(multi=True)
        )


def _filter_door(value, param="display_name.search"):
    field = SearchField(param=param)
    return handle_or_query(field, {}, Search(), value, sample=None)


class TestFilterDoorEmptyOperandIs400:
    """The engine half: handle_or_query rejects an empty OR-operand on search."""

    @pytest.mark.parametrize("value", [
        "nature|",        # trailing — the prod repro
        "|nature",        # leading
        "cancer||treatment",  # doubled
        "nature| ",       # whitespace-only operand
        "!",              # bare bang = negation of nothing = empty operand
        "!cancer|",       # negated list with a trailing empty
        "!|cancer",       # negated list with a leading empty
    ])
    def test_empty_operand_raises(self, value):
        with pytest.raises(APIQueryParamsError, match="empty OR operand"):
            _filter_door(value)

    @pytest.mark.parametrize("value", [
        "dog|cat",
        "!dog",
        "!dog|cat",
        "!dog|!cat",
        "dog cat|fish",
    ])
    def test_legitimate_values_still_build(self, value):
        s = _filter_door(value)
        assert s.to_dict().get("query")  # a real query was attached

    def test_exact_door_covered_too(self):
        with pytest.raises(APIQueryParamsError, match="empty OR operand"):
            _filter_door("cancer|", param="display_name.search.exact")

    def test_non_search_fields_keep_the_old_noop_behavior(self):
        # On a term field an empty operand matches nothing (harmless, since
        # forever); 400ing it would break silently-working queries. Pin the
        # scoping so the guard never quietly widens.
        field = TermField(param="type")
        s = handle_or_query(field, {}, Search(), "journal-article|", sample=None)
        assert s.to_dict()  # built, no raise


class TestParamDoorPipeLifted:
    """validate_search_param no longer bans `|`; it bans the empty operand."""

    @pytest.mark.parametrize("args", [
        {"search": "dog|cat"},
        {"search.title": "dog|cat"},
        {"search.title_and_abstract.exact": "dog|cat"},
        {"search.title": "!dog|cat"},
    ])
    def test_pipe_is_accepted(self, args):
        validate_search_param(FakeRequest(args))  # must not raise

    @pytest.mark.parametrize("args", [
        {"search": "dog|"},
        {"search.title": "|dog"},
        {"search.title_and_abstract.exact": "cancer||treatment"},
        {"search.title.exact": "!cancer|"},
    ])
    def test_empty_operand_raises(self, args):
        with pytest.raises(APIQueryParamsError, match="empty OR operand"):
            validate_search_param(FakeRequest(args))

    def test_semantic_pipe_is_literal_text_not_an_operator(self):
        # search.semantic is a natural-language door with no value operators;
        # a pipe there is just text, so no OR-split and no empty-operand 400.
        validate_search_param(FakeRequest({"search.semantic": "dogs|cats and pets|"}))


class TestBuildSearchValueQuery:
    """The param door composes the filter door's value operators."""

    def test_plain_value_is_the_same_query_as_before_the_refactor(self):
        got = build_search_value_query("works", "dog", None, None,
                                       skip_citation_boost=True)
        want = full_search_query("works", "dog", skip_citation_boost=True)
        assert got.to_dict() == want.to_dict()

    def test_negated_value_is_the_negated_plain_query(self):
        got = build_search_value_query("works", "!dog", None, None,
                                       skip_citation_boost=True)
        want = _negate(full_search_query("works", "dog", skip_citation_boost=True))
        assert got.to_dict() == want.to_dict()

    def test_or_is_a_should_group_of_the_per_operand_queries(self):
        got = build_search_value_query("works", "dog|cat", None, None,
                                       skip_citation_boost=True).to_dict()
        assert got["bool"]["minimum_should_match"] == 1
        assert got["bool"]["should"] == [
            full_search_query("works", "dog", skip_citation_boost=True).to_dict(),
            full_search_query("works", "cat", skip_citation_boost=True).to_dict(),
        ]

    def test_negated_or_is_not_of_the_group(self):
        # `!a|b` = NOT (a OR b) — the filter door's whole-list negation.
        from elasticsearch_dsl import Q

        group = Q(
            "bool",
            should=[
                full_search_query("works", "dog", skip_citation_boost=True),
                full_search_query("works", "cat", skip_citation_boost=True),
            ],
            minimum_should_match=1,
        )
        got = build_search_value_query("works", "!dog|cat", None, None,
                                       skip_citation_boost=True)
        assert got.to_dict() == _negate(group).to_dict()

    def test_scoped_or_uses_the_scoped_builder(self):
        got = build_search_value_query("works", "dog|cat", "title", "default",
                                       skip_citation_boost=True).to_dict()
        assert got["bool"]["should"] == [
            scoped_search_query("dog", "title", "default",
                                skip_citation_boost=True).to_dict(),
            scoped_search_query("cat", "title", "default",
                                skip_citation_boost=True).to_dict(),
        ]

    def test_exact_or_uses_the_exact_builder(self):
        got = build_search_value_query("works", "dog|cat", None, "exact",
                                       skip_citation_boost=True).to_dict()
        assert got["bool"]["should"][0] == full_search_query_exact(
            "dog", skip_citation_boost=True
        ).to_dict()

    def test_mid_list_bang_is_the_filter_doors_error(self):
        with pytest.raises(APIQueryParamsError, match="beginning of an OR"):
            build_search_value_query("works", "dog|!cat", None, None,
                                     skip_citation_boost=True)

    def test_empty_operand_raises_for_direct_callers_too(self):
        with pytest.raises(APIQueryParamsError, match="empty OR operand"):
            build_search_value_query("works", "dog|", None, None,
                                     skip_citation_boost=True)

    def test_scope_check_still_enforced_per_operand(self):
        with pytest.raises(APIQueryParamsError, match="only supported for /works"):
            build_search_value_query("sources", "dog|cat", "title", "default",
                                     skip_citation_boost=True)
