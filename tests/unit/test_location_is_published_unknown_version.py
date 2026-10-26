"""A copy whose version is unknown is not the published version (oxjob #1870).

ES stores such a copy with is_published null (is_accepted false) inside
`locations_full`, but false as primary_location / best_oa_location. Before #1870 the
same copy read null in `locations[]` and false as primary_location on 28% of works, and
`filter=locations.is_published:false` missed every work whose only non-published copy
had no version (87.5M works found where 192.9M qualify). No ES needed.
"""
from elasticsearch_dsl import Search

from core.filter import filter_records
from works.fields import fields_dict
from works.schemas import LocationSchema


def _query(value):
    return filter_records(fields_dict, [{"locations.is_published": value}], Search()).to_dict()["query"]


def test_false_also_matches_copies_that_are_not_accepted():
    q = str(_query("false"))
    assert "'locations_full.is_published': False" in q
    assert "'locations_full.is_accepted': False" in q


def test_true_is_a_plain_term():
    q = str(_query("true"))
    assert "locations_full.is_published" in q
    assert "is_accepted" not in q


def _dump(**loc):
    loc.setdefault("native_id", "10.1/x")
    loc.setdefault("provenance", "crossref")
    return LocationSchema().dump(type("Loc", (), loc)())


def test_unknown_version_serves_false_not_null():
    d = _dump(version=None, is_accepted=False, is_published=None)
    assert d["is_published"] is False
    assert d["is_accepted"] is False


def test_stored_values_are_kept():
    d = _dump(version="publishedVersion", is_accepted=True, is_published=True)
    assert d["is_published"] is True and d["is_accepted"] is True
    d = _dump(version="acceptedVersion", is_accepted=True, is_published=False)
    assert d["is_published"] is False and d["is_accepted"] is True


def test_missing_flags_follow_version():
    d = _dump(version="publishedVersion")
    assert d["is_published"] is True and d["is_accepted"] is True
