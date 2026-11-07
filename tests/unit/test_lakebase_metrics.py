"""oxjob #2082: the Lakebase metrics overlay (fwci, citation_normalized_percentile, cited_by_percentile_year)."""
import json
from unittest import mock

from works import lakebase

DOC = {"id": "https://openalex.org/W1", "fwci": 1.5,
       "citation_normalized_percentile": {"value": 0.5, "is_in_top_1_percent": False, "is_in_top_10_percent": False},
       "cited_by_percentile_year": {"min": 40, "max": 45}}


def test_apply_metrics_overrides_all_three():
    out = lakebase.apply_metrics(dict(DOC), (1, 2.25, True, 0.97, False, True, True, 91, 95))
    assert out["fwci"] == 2.25
    assert out["citation_normalized_percentile"] == {"value": 0.97, "is_in_top_1_percent": False,
                                                     "is_in_top_10_percent": True}
    assert out["cited_by_percentile_year"] == {"min": 91, "max": 95}


def test_apply_metrics_nulls_follow_the_row():
    out = lakebase.apply_metrics(dict(DOC), (1, None, False, None, None, None, False, None, None))
    assert out["fwci"] is None
    assert out["citation_normalized_percentile"] is None
    assert out["cited_by_percentile_year"] is None


def test_no_metrics_row_keeps_the_doc():
    assert lakebase.apply_metrics(dict(DOC), (None,) * 9) == DOC
    assert lakebase.apply_metrics(dict(DOC), None) == DOC


def test_overlay_query_joins_metrics_when_on():
    row = (json.dumps(DOC), 1, 3.0, True, 0.9, False, True, True, 80, 85)
    with mock.patch.object(lakebase, "METRICS_OVERLAY", True), \
            mock.patch.object(lakebase, "_metrics_off_until", 0.0), \
            mock.patch.object(lakebase, "_query_one", return_value=row) as q:
        doc = lakebase.get_work_doc(9)
    assert "lakebase_work_metrics" in q.call_args[0][0]
    assert "lakebase_works_docs_1" in q.call_args[0][0]
    assert doc["fwci"] == 3.0 and doc["cited_by_percentile_year"] == {"min": 80, "max": 85}


def test_overlay_error_falls_back_to_plain_doc_and_pauses():
    calls = []

    def fake(sql, params):
        calls.append(sql)
        if "lakebase_work_metrics" in sql:
            raise RuntimeError("relation does not exist")
        return (json.dumps(DOC),)

    with mock.patch.object(lakebase, "METRICS_OVERLAY", True), \
            mock.patch.object(lakebase, "_metrics_off_until", 0.0), \
            mock.patch.object(lakebase, "_query_one", side_effect=fake):
        assert lakebase.get_work_doc(9) == DOC
        assert lakebase.get_work_doc(9) == DOC   # paused: no second try at the join
    assert sum("lakebase_work_metrics" in s for s in calls) == 1


def test_overlay_off_uses_plain_query():
    with mock.patch.object(lakebase, "METRICS_OVERLAY", False), \
            mock.patch.object(lakebase, "_query_one", return_value=(json.dumps(DOC),)) as q:
        assert lakebase.get_work_doc(9) == DOC
    assert "lakebase_work_metrics" not in q.call_args[0][0]


def test_config_var_turns_it_off():
    with mock.patch.object(lakebase, "METRICS_OVERLAY", True), \
            mock.patch.dict("os.environ", {"LAKEBASE_METRICS_OVERLAY": "0"}):
        assert not lakebase.metrics_overlay_on()
