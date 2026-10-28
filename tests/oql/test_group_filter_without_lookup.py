"""A group filter on the groups' own records needs a lookup in their own index. A split by cited work (#1513) has
none, and answered a 500 (`ValueError: no query-time join configured for entity 'works'`, Sentry
OPENALEX-ELASTIC-API-2A, 2026-10-28); it now answers a refusal that says what to do instead (oxjob #1598)."""
import pytest

from query_translation import analytics as A
from query_translation.oqo import OQO, GroupBy, LeafFilter


def test_a_filter_on_cited_works_own_records_is_refused_not_a_500(monkeypatch):
    from works.fields import fields_dict

    def no_search(*a, **k):
        raise AssertionError("refused before any search")
    monkeypatch.setattr(A, "_search", no_search)
    oqo = OQO(get_rows="works", group_by=[GroupBy(column_id="referenced_works",
                                                  where=LeafFilter("publication_year", 2020, ">"))])
    with pytest.raises(A.AnalyticsError) as e:
        A.run(oqo, index_name="works", connection=None, fields_dict=fields_dict, base_query={"match_all": {}})
    assert e.value.code == "group_filter_not_available"
    assert "own records" in e.value.message


def test_authors_still_have_their_own_records():
    assert A._has_own_fields("authors") and not A._has_own_fields("works")
