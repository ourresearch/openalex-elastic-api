"""`is_authors_truncated` on works (oxjob #1043, Zendesk 6379).

A list of works shows each work's first 100 authorships; the single-work endpoint shows every authorship the work
keeps (`authorships_full`). The flag tells a list reader the list was cut. Walden never wrote the old Logstash
`authorships_truncated`, so the key was missing from every response while `select=is_authors_truncated` still
accepted it. It is now computed from `authors_count`, which every works doc carries. No ES needed.
"""
from elasticsearch_dsl.utils import AttrDict

from works.schemas import WorksSchema


def work_doc(n_authors, authors_count=None, shown=100):
    full = [{"author": {"id": f"https://openalex.org/A{i}"}, "author_position": "middle"} for i in range(n_authors)]
    doc = {
        "id": "https://openalex.org/W1",
        "authorships": full[:shown],
        "authorships_full": full,
    }
    if authors_count != "absent":
        doc["authors_count"] = n_authors if authors_count is None else authors_count
    return AttrDict(doc)


def dump_list(doc, only=("id", "authorships", "is_authors_truncated")):
    return WorksSchema(context={}, only=only).dump(doc)


def test_list_work_over_100_authors_is_truncated():
    out = dump_list(work_doc(252))
    assert len(out["authorships"]) == 100
    assert out["is_authors_truncated"] is True


def test_list_work_with_100_or_fewer_authors_is_not_truncated():
    assert dump_list(work_doc(100))["is_authors_truncated"] is False
    assert dump_list(work_doc(3))["is_authors_truncated"] is False
    assert dump_list(work_doc(0))["is_authors_truncated"] is False


def test_list_work_at_the_5000_cap_is_truncated():
    # walden keeps 5,000 authorships and authors_count = least(n, 5000)
    assert dump_list(work_doc(5000))["is_authors_truncated"] is True


def test_select_only_the_flag_still_computes_it():
    out = dump_list(work_doc(127), only=("id", "is_authors_truncated"))
    assert out == {"id": "https://openalex.org/W1", "is_authors_truncated": True}


def test_list_doc_without_authors_count_gives_null():
    assert dump_list(work_doc(252, authors_count="absent"))["is_authors_truncated"] is None


def test_single_work_shows_every_authorship_and_no_flag():
    out = WorksSchema(context={"single_record": True}, only=("id", "authorships", "is_authors_truncated")).dump(
        work_doc(252)
    )
    assert len(out["authorships"]) == 252
    assert "is_authors_truncated" not in out


def test_single_work_select_of_the_flag_returns_just_the_id():
    # as in v1: select=id,is_authors_truncated on /works/W... gives the id alone
    out = WorksSchema(context={"single_record": True}, only=("id", "is_authors_truncated")).dump(work_doc(112))
    assert out == {"id": "https://openalex.org/W1"}
