"""Forms Haiku reached for when writing OQL, now accepted (oxjob #1555, Jason 2026-10-08:
"let's pave the cow paths"). Each case: what Haiku wrote reads the same as the form we
already had. Rounds and counts: oxjob #1555 EXPLORE.md, "Cow paths".
"""
import pytest

from query_translation.oql_lang import parse
from query_translation.oql_pipeline import render_pipeline_line
from query_translation.oqo_canonicalizer import canonicalize_oqo


def _canon(q):
    return canonicalize_oqo(parse(q)).to_dict()


SAME = [
    # a yes/no field alone is true; `not` makes it false
    ("get works where has DOI and global south", "get works where has DOI is true and global south is true"),
    ("get works where not has DOI and type is article", "get works where has DOI is false and type is article"),
    ("get works where top 1% cited; then summarize using count",
     "get works where top 1% cited is true; then summarize using count"),
    # a closed vocabulary by name
    ("get works where continent is (Africa)", "get works where continent is (Q15)"),
    ('get works where country is ("United Kingdom" or Kenya)', "get works where country is (GB or KE)"),
    # `none` means no value
    ("get works where funder is not (none)", "get works where funder is not unknown"),
    # start from a saved list of works
    ("get works in (col_mylist); then group those works by year",
     "get works where openalex id is in (col_mylist); then group those works by year"),
    ("get works in the collection [My list](col_mylist) where published after 2020",
     "get works where openalex id is in (col_mylist) and published after 2020"),
    # more splits in one step
    ("get works where published after 2020; then group those works by author and by year",
     "get works where published after 2020; then group those works by author; then group those works again by year"),
    ("get works where published after 2020; then group those works by publisher then by year",
     "get works where published after 2020; then group those works by publisher; then group those works again by year"),
    # `IT` in a comparison is Italy, not the pronoun
    ("get works where published after 2020; then compare country (US) versus (IT)",
     "get works where published after 2020; then group those works by country in (US, IT)"),
]


@pytest.mark.parametrize("cow,road", SAME)
def test_cow_path_reads_like_the_road(cow, road):
    assert _canon(cow) == _canon(road)


def test_a_saved_list_of_works_echoes_as_a_start():
    echo = render_pipeline_line(canonicalize_oqo(parse("get works in (col_mylist) where published after 2020")))
    assert echo == "get works in the collection (col_mylist) where published after 2020"
    assert _canon(echo) == _canon("get works in (col_mylist) where published after 2020")


# Jason 2026-10-08: the splits read as one step, `by author and year` (no second `by`);
# `and by` after a group filter or bins; the Oxford comma for three. Either is accepted.
ECHOES = [
    ("get works where published after 2015; then group by author; then group again by year; then summarize using count",
     "get works where published after 2015; then, group those works by author and year; finally, summarize using count"),
    ("get works where published after 2015; then group those works by year and by type and by country",
     "get works where published after 2015; then, group those works by year, type, and country"),
    ("get works where title-abstract has kelp; then group by author where count of those works is above 10; "
     "then group again by year",
     "get works where title-abstract has (kelp); then, group those works by author where count of those "
     "works is above 10 and by year"),
    ("get works where published after 2015; then group those works into citation count bins at (1, 10); then group again by year",
     "get works where published after 2015; then, group those works into citation count bins at (1, 10) and by year"),
    ("get works where published after 2020; then compare type article versus review by year and by country",
     "get works where published after 2020; then, compare type [article](article) versus [review](review) by year and country"),
]


@pytest.mark.parametrize("q,echo", ECHOES)
def test_splits_read_as_one_step(q, echo):
    o = canonicalize_oqo(parse(q))
    assert render_pipeline_line(o) == echo
    assert _canon(echo) == o.to_dict()


# Round 2 (Haiku 5.5, 300 fresh questions, guide in today's echo)
SAME_R2 = [
    # the echo's own set form after another condition (was a parse error: a bug)
    ("get works where source type is [journal](journal) and it cites a work in the set (works where published after 2020)",
     "get works where source type is journal and it cites works in (get works where published after 2020)"),
    ("get works where institution is I63966007 and it doesn't cite any work in the set (works where published after 2020)",
     "get works where institution is I63966007 and it doesn't cite works in (get works where published after 2020)"),
    # a bare one-word wildcard is exact text, as if quoted
    ("get works where title-abstract has (adolescen* OR teen*)",
     'get works where title-abstract has ("adolescen*" OR "teen*")'),
    # `institution continent`, as `institution country`; `ID` for the OpenAlex id
    # (registry aliases, PROPERTIES_VERSION 15.1.0 on the branch, Jason's yes 2026-10-08)
    ("get works where institution continent is Q15", "get works where continent is Q15"),
    ("get works where ID is (W2741809807 or W2100837269)",
     "get works where openalex id is (W2741809807 or W2100837269)"),
    # a DOI keeps its parentheses
    ("get works where DOI is (10.1016/S0140-6736(20)30183-5 or 10.1056/NEJMoa2034577)",
     'get works where DOI is ("10.1016/S0140-6736(20)30183-5" or "10.1056/NEJMoa2034577")'),
]


@pytest.mark.parametrize("cow,road", SAME_R2)
def test_cow_path_round_2(cow, road):
    assert _canon(cow) == _canon(road)


def test_a_parenthesis_after_a_plain_word_is_still_a_group():
    assert _canon("get works where title has (sleep (REM) cycles)") == _canon(
        "get works where title has (sleep AND REM AND cycles)")


# Yes/no flags as sentences, the June 2026 phrasing, accepted again (Jason 2026-10-08:
# "accept either"); canonical stays `<flag> is true|false`.
SENTENCES = [
    ("get works where it's open access and it doesn't have a DOI",
     "get works where open access is true and has DOI is false"),
    ("get works where it has DOI", "get works where has DOI is true"),
    ("get works where it is not retracted", "get works where retracted is false"),
    ("get works where it isn't retracted", "get works where retracted is false"),
    ("get works where it has no abstract", "get works where has abstract is false"),
    ("get works where it's in the top 10% by citations", "get works where top 10% cited is true"),
    ("get works where published after 2020; then compare it's open access versus it isn't open access",
     "get works where published after 2020; then compare open access versus not open access"),
]


@pytest.mark.parametrize("sentence,road", SENTENCES)
def test_a_flag_as_a_sentence(sentence, road):
    assert _canon(sentence) == _canon(road)


def test_a_relation_still_reads_as_a_relation():
    # `it's cited by` is the relation, not a flag sentence
    assert _canon("get works where it's cited by (W2741809807)") != _canon("get works where has DOI is true")
    echo = render_pipeline_line(canonicalize_oqo(parse("get works where it cites (W2741809807)")))
    assert echo == "get works where it cites (W2741809807)"   # not ((W2741809807))


# After a plain value, a flag sentence, a flag alone, or `not <condition>` starts a new
# condition (each was read as a second value: the yes/no write test found it, 2026-10-08).
AFTER_A_VALUE = [
    ("get works where type is [article](article) and published in 2021 and it's not open access",
     "get works where type is article and published in 2021 and open access is false"),
    ("get works where type is article and has DOI and published in 2020",
     "get works where type is article and has DOI is true and published in 2020"),
    ("get works where country is [Ghana](GH) and not retracted",
     "get works where country is GH and retracted is false"),
    ("get works where type is article and not year is 2020",
     "get works where type is article and year is not 2020"),
]


@pytest.mark.parametrize("q,road", AFTER_A_VALUE)
def test_a_condition_after_a_plain_value(q, road):
    assert _canon(q) == _canon(road)


# Jason 2026-10-08: a yes/no flag echoes as its sentence; flags with none keep `is true|false`.
FLAG_ECHOES = [
    ("get works where country is GH and retracted is false and has abstract is true",
     "get works where country is [Ghana](GH) and it has an abstract and it's not retracted"),
    ("get works where global south is true and PubMed is false",
     "get works where it's from the global south and it's not indexed by PubMed"),
]


@pytest.mark.parametrize("q,echo", FLAG_ECHOES)
def test_a_flag_echoes_as_its_sentence(q, echo):
    o = canonicalize_oqo(parse(q))
    assert render_pipeline_line(o) == echo
    assert _canon(echo) == o.to_dict()


# Round 3 (Haiku 5.5, guide v4, 300 fresh questions, 2026-10-08): 286 valid; these are the
# misses that were ours.
ROUND_3 = [
    # a flag sentence from the flag's own name (its June sentence is `it's in the top 10%
    # by citations`)
    ("get works where it's top 10% cited and published after 2020",
     "get works where top 10% cited is true and published after 2020"),
    ("get works where it's not top 1% cited", "get works where top 1% cited is false"),
    ("get works where it has PMCID and it doesn't have references and it's not paratext",
     "get works where has PMCID is true and has references is false and paratext is false"),
    ("get sources where it's DOAJ", "get sources where DOAJ is true"),
    # a license as a link: the echo writes one, so it has to read one back
    ("get works where license is [CC BY](cc-by)", "get works where license is cc-by"),
    ("get works where license is ([CC-BY](cc-by) or [CC-BY-SA](cc-by-sa))",
     "get works where license is (cc-by or cc-by-sa)"),
]


@pytest.mark.parametrize("cow,road", ROUND_3)
def test_cow_path_round_3(cow, road):
    assert _canon(cow) == _canon(road)


def test_every_linked_value_reads_back():
    """Whatever the echo writes as a link parses back to the same query (licenses are
    strings the echo links)."""
    for q in ["get works where license is cc-by", "get works where best OA license is cc-by-nc",
              "get works where any location license is cc-by-sa"]:
        o = canonicalize_oqo(parse(q))
        echo = render_pipeline_line(o)
        assert "](cc-by" in echo
        assert _canon(echo) == o.to_dict()


def test_a_compared_negation_reads_is_not():
    """Jason 2026-10-09: `country is not [India](IN)` reads better than `not country
    [India](IN)` (which Haiku wrote 4 times in round 3; accepted, never echoed)."""
    echo = render_pipeline_line(canonicalize_oqo(parse(
        "get works where published after 2020; then compare country IN versus not country IN")))
    assert echo.endswith("compare country [India](IN) versus country is not [India](IN)")
    assert _canon(echo) == _canon("get works where published after 2020; then compare country IN "
                                  "versus not country IN")


def test_that_country_is_a_valid_group_filter():
    from query_translation.validator import validate_oqo
    o = canonicalize_oqo(parse("get works where published after 2020; then group those works by "
                               "country where that country is not [Iran](IR)"))
    assert validate_oqo(o).valid


# The map's cow paths (2026-10-09): Opus 5.5 wrote one query for each of #1602's 1,457
# map questions (oxjob #1555 EXPLORE.md, "Map fit"); these are the refusals that were ours.
MAP_FIT = [
    # a link right after a relation verb starts a new condition
    ("get works where title has kelp and it cites [Attention Is All You Need](W2963403868)",
     "get works where title has kelp and it cites (W2963403868)"),
    ("get works where author is [Jane Smith](A5023888391) and it cites [A paper: its subtitle](W2100837269)",
     "get works where author is (A5023888391) and it cites (W2100837269)"),
    ("get works where it cites [Attention](W2963403868) or it's cited by [Attention](W2963403868)",
     "get works where it cites (W2963403868) or it's cited by (W2963403868)"),
    # `and by` after a group filter that ends in a value: the next split
    ("get works where published after 2020; then group those works by institution where country is [Canada](CA) and by language",
     "get works where published after 2020; then group those works by institution where country is CA and by language"),
    ("get works where published after 2019; then group those works by author where last known institution is not "
     "[Harvard University](I136199984) and by year",
     "get works where published after 2019; then group those works by author where last known institution is not "
     "(I136199984); then group those works again by year"),
    # a set of a collection's works, the way the echo writes it
    ("get works where it cites a work in the set (works in the collection [My seeds](col_seeds))",
     "get works where it cites a work in the set (works where openalex id is in (col_seeds))"),
    ("get works where topic is in the set (topics of works in the collection [Gov](col_gov))",
     "get works where topic is in the set (topics of works where openalex id is in (col_gov))"),
    # a relation as a compared thing
    ("get works where published since 2000; then compare institution [UM](I27837315) versus it's cited by a work "
     "in the set (works where institution is (I27837315)) using count",
     "get works where published since 2000; then compare institution is (I27837315) versus it's cited by a work "
     "in the set (works where institution is (I27837315)) using count"),
    # yes/no sentences: `fulltext` as one word, `in` before an index's name
    ("get works where it has fulltext", "get works where has full text is true"),
    ("get works where it doesn't have fulltext", "get works where has full text is false"),
    ("get works where it's in CWTS core or it's not in PubMed",
     "get works where CWTS core is true or PubMed is false"),
    # whether a field has a value: `it has a funder`, `it has no SDG`
    ("get works where it has an SDG", "get works where SDG is not unknown"),
    ("get works where it has no SDG and published after 2020", "get works where SDG is unknown and published after 2020"),
    ("get works where title has kelp and it doesn't have a funder",
     "get works where title has kelp and funder is unknown"),
    # a code written as a link
    ("get works where any location version is ([accepted version](acceptedVersion) or "
     "[published version](publishedVersion))",
     "get works where any location version is (acceptedVersion or publishedVersion)"),
    ("get authors where past institutions type is [education](education)",
     "get authors where past institutions type is education"),
    # two-letter continent codes
    ("get works where continent is ([Africa](AF) or (EU))", "get works where continent is (Q15 or Q46)"),
]


@pytest.mark.parametrize("cow,road", MAP_FIT)
def test_cow_path_map_fit(cow, road):
    assert _canon(cow) == _canon(road)


@pytest.mark.parametrize("q", [
    "get works where it cites a work in the set (works in the collection (col_seeds))",
    "get works where published since 2000; then, compare (institution is (I27837315) and published since 2020) "
    "versus it's cited by a work in the set (works where institution is (I27837315)) using count by source",
])
def test_the_echo_reads_back(q):
    """The echo's own output parses to the same query: the set of a collection's works,
    and a set inside a comparison (whose `is` stays: it's a query of its own)."""
    o = canonicalize_oqo(parse(q))
    echo = render_pipeline_line(o)
    assert "in the set (works where institution (" not in echo
    assert _canon(echo) == o.to_dict()


@pytest.mark.parametrize("q,echo", [
    # authors, institutions ... echo their own field names (oxjob #1555; were raw column
    # ids and works words)
    ("get authors where subfield is (1702)", "get authors where subfield is [Artificial Intelligence](1702)"),
    ("get institutions where country is (CA)", "get institutions where country is [Canada](CA)"),
    ("get authors where institution country is (BR)", "get authors where institution country is [Brazil](BR)"),
    ("get keywords where related topics is (T10878)", "get keywords where related topics is (T10878)"),
    ("get topics where parent subfield is (2712)",
     "get topics where parent subfield is [Endocrinology, Diabetes and Metabolism](2712)"),
])
def test_non_works_fields_echo_their_own_names(q, echo):
    import sys
    sys.path.insert(0, "docs/oql")
    from regen_corpus_oql import make_resolver
    o = canonicalize_oqo(parse(q))
    got = render_pipeline_line(o, make_resolver({}))
    assert got == echo
    assert _canon(got) == o.to_dict()


def test_topics_parent_subfield_is_the_topics_own_column():
    """`parent subfield` (topics' registry name) read as works' primary_topic.subfield.id
    (on production too, 2026-10-09)."""
    o = canonicalize_oqo(parse("get topics where parent subfield is (2712)"))
    assert o.filter_rows[0].column_id == "subfield.id"


@pytest.mark.parametrize("q", [
    "institutions where country is (DE) group by type",
    "sources group by publisher",
    "authors where h-index is above 50 group by last known institution",
])
def test_a_non_works_group_by_echo_reads_back(q):
    """A classic group-by on authors, institutions or sources echoes `then, group those
    institutions by ...`, which must parse back (live regression after step 1, found by
    #1494's gold re-render 2026-10-09); only a walk to non-works things needs its works
    before a split."""
    o = canonicalize_oqo(parse(q))
    echo = render_pipeline_line(o)
    assert "; then, group those " in echo
    assert _canon(echo) == o.to_dict()


def test_a_split_after_a_walk_still_needs_the_works():
    from query_translation.diagnostics import OQLError
    with pytest.raises(OQLError) as e:
        parse("get works where published after 2020; then get each author of those works; then group those authors by year")
    assert e.value.code == "OQL_SPLIT_NEEDS_WORKS"
