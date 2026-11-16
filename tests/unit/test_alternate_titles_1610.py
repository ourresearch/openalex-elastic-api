"""Works: alternate_titles, and title searches that read it (oxjob #1610, ZD 25872).

A work's Crossref record can carry several titles (an Arabic title and its English translation). Walden now
keeps the others in `alternate_titles`; the API serves them (always a list) and every works search that reads
the title reads them too, as one best-of title clause: `dis_max` of the search as typed and the same search on
`alternate_titles` alone, at the title field's weight, so a work matching by both titles scores once.
Shape tests only (no ES): `.to_dict()` of the emitted query.
"""
import copy
import json
import logging

import pytest
from elasticsearch_dsl import AttrDict

from core.keyword_search import text_fields_for
from core.search import full_search_query, full_search_query_exact, scoped_search_query
from core.utils import check_select_field
from works.fields import fields_dict
from works.schemas import WorksSchema

logging.getLogger("core.merged_ids").setLevel(logging.CRITICAL)  # no cluster here: IDs serve as given

ENGLISH = "Technological competencies required for the intermediate and high school female teachers"


def _fields_read(node):
    """Every field name the query reads (match, match_phrase, query_string, multi_match, intervals)."""
    out = set()
    if isinstance(node, dict):
        for kind in ("match", "match_phrase", "intervals", "prefix", "wildcard"):
            if kind in node and isinstance(node[kind], dict):
                out |= set(node[kind].keys())
        for kind in ("query_string", "multi_match"):
            if kind in node:
                qs = node[kind]
                out |= {f.split("^")[0] for f in qs.get("fields", [])}
                if "default_field" in qs:
                    out.add(qs["default_field"])
        for v in node.values():
            out |= _fields_read(v)
    elif isinstance(node, list):
        for v in node:
            out |= _fields_read(v)
    return out


def _two_titles(d):
    """Unwrap the top-level dis_max; return (typed, alternate)."""
    assert set(d) == {"dis_max"}, d
    typed, alternate = d["dis_max"]["queries"]
    return typed, alternate


def _field_query(param, value):
    f = copy.deepcopy(fields_dict[param])
    f.value = value
    return f.build_query().to_dict()


# --- the scoped searches (search.title=, search.title_and_abstract=, and their .exact) ----------------------

@pytest.mark.parametrize("search_type,title,alt", [
    ("default", "display_name", "alternate_titles"),
    ("exact", "display_name.no_stem", "alternate_titles.no_stem"),
])
@pytest.mark.parametrize("terms", [ENGLISH, f'"{ENGLISH}"', "whiteboard AND teachers", "white*"])
def test_title_search_reads_both_titles_in_one_best_of_clause(search_type, title, alt, terms):
    if terms == "white*" and search_type == "default":
        pytest.skip("a wildcard needs the exact search")
    typed, alternate = _two_titles(scoped_search_query(terms, "title", search_type, skip_citation_boost=True).to_dict())
    assert _fields_read(typed) == {title}
    assert _fields_read(alternate) == {alt}


@pytest.mark.parametrize("search_type,fields,alt", [
    ("default", {"display_name", "abstract"}, "alternate_titles"),
    ("exact", {"display_name.no_stem", "abstract.no_stem"}, "alternate_titles.no_stem"),
])
def test_title_and_abstract_repeats_only_the_title_side(search_type, fields, alt):
    q = scoped_search_query(ENGLISH, "title_and_abstract", search_type, skip_citation_boost=True).to_dict()
    typed, alternate = _two_titles(q)
    assert _fields_read(typed) == fields
    assert _fields_read(alternate) == {alt}  # the abstract runs once


def test_the_alternate_title_weighs_as_the_title():
    # Two-field plain search: the title's match boost is 1, so the alternate clause is not reweighted.
    _, alternate = _two_titles(scoped_search_query(ENGLISH, "title_and_abstract", "default", True).to_dict())
    assert "bool" not in alternate or "boost" not in alternate["bool"]
    # search= (three fields) plain path: the title weighs 1.5, so the alternate clause carries 1.5.
    _, alternate = _two_titles(full_search_query("works", ENGLISH, skip_citation_boost=True).to_dict())
    assert alternate["bool"]["boost"] == 1.5
    assert _fields_read(alternate) == {"alternate_titles"}
    # Boolean path: the title field has no boost there, and neither has the alternate clause.
    _, alternate = _two_titles(full_search_query("works", "whiteboard AND teachers", True).to_dict())
    assert "boost" not in alternate.get("bool", {})


def test_search_and_its_exact_form_read_the_alternate_titles():
    typed, alternate = _two_titles(full_search_query("works", ENGLISH, skip_citation_boost=True).to_dict())
    assert _fields_read(typed) == {"display_name", "abstract", "fulltext"}
    assert _fields_read(alternate) == {"alternate_titles"}
    typed, alternate = _two_titles(full_search_query_exact(ENGLISH, skip_citation_boost=True).to_dict())
    assert _fields_read(typed) == {"display_name.no_stem", "abstract.no_stem", "fulltext.no_stem"}
    assert _fields_read(alternate) == {"alternate_titles.no_stem"}


def test_the_citation_boost_wraps_the_pair_once():
    q = scoped_search_query(ENGLISH, "title", "default").to_dict()
    assert set(q) == {"function_score"}
    _two_titles(q["function_score"]["query"])
    assert json.dumps(q).count("function_score") == 1


def test_whole_query_not_drops_a_work_holding_the_word_in_any_title():
    q = scoped_search_query("NOT whiteboard", "title", "default", skip_citation_boost=True).to_dict()
    assert q["bool"]["must"] == [{"match_all": {}}]
    (positive,) = q["bool"]["must_not"]
    typed, alternate = _two_titles(positive)
    assert _fields_read(typed) == {"display_name"} and _fields_read(alternate) == {"alternate_titles"}


# --- the filters (title.search, title.search.exact, display_name.search, title_and_abstract.search) --------

@pytest.mark.parametrize("param,title,alt", [
    ("title.search", "display_name", "alternate_titles"),
    ("title.search.exact", "display_name.no_stem", "alternate_titles.no_stem"),
    ("display_name.search", "display_name", "alternate_titles"),
    ("display_name.search.exact", "display_name.no_stem", "alternate_titles.no_stem"),
    ("title_and_abstract.search", "display_name", "alternate_titles"),
    ("title_and_abstract.search.exact", "display_name.no_stem", "alternate_titles.no_stem"),
])
def test_title_filters_read_the_alternate_titles(param, title, alt):
    q = _field_query(param, ENGLISH)
    assert alt in _fields_read(q) and title in _fields_read(q)
    assert '"dis_max"' in json.dumps(q)


@pytest.mark.parametrize("param", ["abstract.search", "abstract.search.exact", "raw_author_name.search",
                                   "keyword.search"])
def test_other_works_searches_unchanged(param):
    assert not any(f.startswith("alternate_titles") for f in _fields_read(_field_query(param, "whiteboard")))


def test_other_indexes_unchanged():
    # sources and publishers have their own alternate_titles, searched as the secondary field as before
    q = full_search_query("sources", "nature", skip_citation_boost=True).to_dict()
    assert "dis_max" not in q
    assert "alternate_titles.no_stem" not in json.dumps(full_search_query("publishers", "elsevier").to_dict())


def test_keyword_rule_text_reads_the_alternate_titles():
    assert text_fields_for("default", False) == ["display_name", "alternate_titles", "abstract^0.1"]
    assert text_fields_for("exact", True) == [
        "display_name.no_stem", "alternate_titles.no_stem", "abstract.no_stem^0.1", "fulltext.no_stem^0.05"]


# --- the work record ----------------------------------------------------------------------------------------

def _doc(**fields):
    from works.lakebase import LakebaseHit

    return LakebaseHit(fields)


@pytest.mark.parametrize("doc,expected", [
    ({}, []),                                            # a doc synced before the field existed
    ({"alternate_titles": None}, []),                   # null never leaks
    ({"alternate_titles": []}, []),
    ({"alternate_titles": [ENGLISH]}, [ENGLISH]),
])
def test_alternate_titles_is_always_a_list(doc, expected):
    out = WorksSchema(only=("id", "alternate_titles")).dump(_doc(id="https://openalex.org/W3164863413", **doc))
    assert out == {"id": "https://openalex.org/W3164863413", "alternate_titles": expected}


def test_an_es_hit_serves_it_too():
    hit = AttrDict({"meta": {"score": None}, "id": "https://openalex.org/W1", "alternate_titles": ["B", "C"]})
    assert WorksSchema(only=("alternate_titles",)).dump(hit) == {"alternate_titles": ["B", "C"]}


def test_select_alternate_titles_is_accepted():
    fields = list(WorksSchema._declared_fields)
    assert fields.index("alternate_titles") == fields.index("display_name") + 1
    check_select_field("alternate_titles", fields)
