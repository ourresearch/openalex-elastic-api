"""Locations entity — engine-side value handling (oxjob #850, 2026-08-30).

Three works-era code paths mishandled the locations entity's plain columns:

  1. License values were force-converted to full-URL license IDs
     (`https://openalex.org/licenses/cc-by`) — a works-index convention (its
     license params all target `*license_id.keyword` es fields). The locations
     index stores the bare short code, so `filter=license:cc-by` silently
     matched nothing.
  2. `version:null` hardcoded an exists-check on `locations.version` for ANY
     field named `version` — wrong es path for the locations entity.
  3. `group_by=version` routed every `version` param through the works-specific
     MultiSearch that terms on `locations.version` — all-zero buckets on the
     locations entity.

No ES needed — these assert on the queries/values the fields build.
"""
from core.group_by.utils import is_works_version_group_by
from locations.fields import fields_dict as locations_fields
from works.fields import fields_dict as works_fields


def test_locations_license_value_stays_bare():
    f = locations_fields["license"]
    for given in ("cc-by", "licenses/cc-by", "https://openalex.org/licenses/cc-by"):
        f.value = given
        assert f._get_formatted_value() == "cc-by", given


def test_works_license_value_still_full_url():
    f = works_fields["locations.license"]
    f.value = "cc-by"
    assert f._get_formatted_value() == "https://openalex.org/licenses/cc-by"


def test_locations_license_term_query_uses_bare_code():
    f = locations_fields["license"]
    f.value = "cc-by"
    q = f.build_query().to_dict()
    assert q == {"term": {"license": "cc-by"}}, q


def test_locations_version_null_uses_own_es_field():
    f = locations_fields["version"]
    f.value = "null"
    q = f.build_query().to_dict()
    assert q == {"bool": {"must_not": [{"exists": {"field": "version"}}]}}, q


def test_works_version_null_still_targets_locations_version():
    f = works_fields["version"]
    f.value = "null"
    q = f.build_query().to_dict()
    assert q == {"bool": {"must_not": [{"exists": {"field": "locations.version"}}]}}, q


def test_group_by_version_override_scoped_to_works():
    """Only works' `version` (es field `locations.version`) takes the bespoke
    group_by_version path; the locations entity's own `version` column must fall
    through to the default terms-agg path."""
    assert is_works_version_group_by(works_fields["version"]) is True
    assert is_works_version_group_by(locations_fields["version"]) is False


def test_locations_full_search_targets_analyzed_title():
    """search= / text.search / default.search route through full_search_query,
    whose locations branch must target the analyzed title.text (v3) with no
    citation boost (locations lack cited_by_count). Before #850's branch they
    fell into the generic else and searched the nonexistent display_name —
    a silent count-0 no-op."""
    from core.search import full_search_query

    q = str(full_search_query("locations-v3", "climate change").to_dict())
    assert "title.text" in q, q
    assert "display_name" not in q, q
    assert "function_score" not in q, q


def test_locations_title_search_targets_analyzed_title():
    f = locations_fields["title.search"]
    f.value = "climate change"
    q = str(f.build_query().to_dict())
    assert "title.text" in q, q
    assert "function_score" not in q, q
