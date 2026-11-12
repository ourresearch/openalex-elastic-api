"""Awards `keywords.id` / `sustainable_development_goals.id` filters and columns (oxjob #2125, topics, keywords and SDGs on grants).

awards-v4 maps `keywords` and `sustainable_development_goals` exactly as the works index does (object, keyword id) and Nightly
Grants stores works' ids (https://openalex.org/keywords/<slug>, https://metadata.un.org/sdg/N), so every form a works filter
accepts must build the same term on awards. No ES needed: these assert on the queries the fields build.
"""
import copy

import pytest

from awards.fields import fields_dict as awards_fields
from works.fields import fields_dict as works_fields

KW = "https://openalex.org/keywords/acute-myeloid-leukemia"
SDG = "https://metadata.un.org/sdg/3"


def _query(fields, param, value):
    f = copy.deepcopy(fields[param])
    f.value = value
    return f.build_query().to_dict()


@pytest.mark.parametrize("param, values", [
    ("keywords.id", ["acute-myeloid-leukemia", "keywords/acute-myeloid-leukemia", KW, "!acute-myeloid-leukemia", "!null"]),
    ("sustainable_development_goals.id", ["3", "sdgs/3", "https://openalex.org/sdgs/3", SDG, "!3", "!null"]),
])
def test_awards_build_the_works_query_for_every_accepted_form(param, values):
    for v in values:
        assert _query(awards_fields, param, v) == _query(works_fields, param, v), (param, v)


def test_the_terms_hit_the_stored_ids():
    # SDG terms go to the `.lower` subfield, as on works (the mapping copies works' `id.lower`)
    assert _query(awards_fields, "sustainable_development_goals.id", "3") == {"term": {"sustainable_development_goals.id.lower": SDG}}
    q = _query(awards_fields, "keywords.id", "acute-myeloid-leukemia")
    assert "keywords.id" in str(q) and "acute-myeloid-leukemia" in str(q)


def test_an_award_serves_works_keyword_and_sdg_objects_and_empty_lists_until_filled():
    from awards.schemas import AwardsSchema
    kw = [{"id": KW, "display_name": "acute myeloid leukemia", "score": 0.968}]
    sdg = [{"id": SDG, "display_name": "Good health and well-being", "score": 0.9858}]
    cols = ("id", "keywords", "sustainable_development_goals")
    award = AwardsSchema(only=cols).dump({"id": "https://openalex.org/G3933536818", "keywords": kw, "sustainable_development_goals": sdg})
    assert award["keywords"] == kw and award["sustainable_development_goals"] == sdg
    bare = AwardsSchema(only=cols).dump({"id": "https://openalex.org/G1"})      # a document Nightly Grants has not re-sent yet
    assert bare["keywords"] == [] and bare["sustainable_development_goals"] == []
