"""OQL words `title-abstract` and `title-abstract-keywords` (oxjobs #1521 + #1512, 2026-10-03).

The hyphen forms are canonical: every render echoes them. The slash forms that were
canonical before (`title/abstract`, `title/abstract/keywords`) and every older alias stay
accepted on input forever. API filter names do not change.
"""
import pytest

from query_translation.oql_lang import parse, render

TA_INPUTS = ["title-abstract", "title/abstract", "title/abs", "title & abstract",
             "title and abstract", "title&abstract", "title_and_abstract",
             "title_and_abstract.search"]
TAK_INPUTS = ["title-abstract-keywords", "title/abstract/keywords", "title/abs/keywords",
              "title abstract keywords", "title_abstract_keywords",
              "title_abstract_keywords.search"]


@pytest.mark.parametrize("word", TA_INPUTS)
def test_title_abstract_spellings_echo_hyphen(word):
    oqo = parse(f"works where {word} has (kelp)")
    assert oqo.filter_rows[0].column_id == "title_and_abstract.search"
    assert render(oqo) == "works where title-abstract has (kelp)"


@pytest.mark.parametrize("word", TAK_INPUTS)
def test_title_abstract_keywords_spellings_echo_hyphen(word):
    oqo = parse(f"works where {word} has (kelp)")
    assert oqo.filter_rows[0].column_id == "title_abstract_keywords.search"
    assert render(oqo) == "works where title-abstract-keywords has (kelp)"


def test_both_words_in_one_query_round_trip():
    oql = "works where title-abstract has (kelp) and title-abstract-keywords has (forest)"
    assert render(parse(oql)) == oql
