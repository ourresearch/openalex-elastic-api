"""Filter values the API couldn't apply answered 200 with a wrong count (oxjob #2140). No ES, no app.

1. A quoted operand in an OR list kept its quotes and matched nothing: doi:"10.1/a"|"10.1/b" answered 0,
   geo.region:"New York"|California answered California alone.
2. A country name or alpha-3 code in a country filter answered 0 (country_code:canada, institutions.country_code:usa).
3. q= without group_by did nothing, so /works?q=cancer answered all 315M works.
4. A bare short id on two filters that store full URLs answered 0 (awards id:G2966666733, ticket 22928;
   authorships.affiliations.institution_ids:I136199984).
5. filter=include_xpac:true was accepted with any value and did nothing; include_xpac=True read as false.

Now each gives the right count or a JSON 400 that says what to use.
"""
import flask
import pytest
from elasticsearch_dsl import Search

from awards.fields import fields_dict as awards_fields
from core.exceptions import APIQueryParamsError
from core.filter import filter_records
from core.params import parse_params
from core.quoted_values import unquote_filter_value
from core.validate import xpac_controls, xpac_flag_value
from institutions.fields import fields_dict as institutions_fields
from query_translation.url_parser import parse_url_to_oqo
from sources.fields import fields_dict as sources_fields
from works.fields import fields_dict as works_fields

app = flask.Flask(__name__)


def _q(fields, key, value):
    return filter_records(fields, [{key: value}], Search()).to_dict()


def _error(fields, key, value):
    with pytest.raises(APIQueryParamsError) as err:
        _q(fields, key, value)
    return str(err.value)


# ---------- 1. quoted operands in an OR list ----------

@pytest.mark.parametrize("value, plain", [
    ('"a"|"b"', "a|b"),
    ('"New York"|California', "New York|California"),
    ('California|"New York"', "California|New York"),
    ('!"New York"|California', "!New York|California"),
    ('"a b|c d"', "a b|c d"),        # quoted whole: OR of the two, as since #363
    ('"New York"', "New York"),
    ('!"New York"', "!New York"),
    ("a|b", "a|b"),
    ('"Diabetes Mellitus, Type 2"', "Diabetes Mellitus, Type 2"),
])
def test_unquote_filter_value(value, plain):
    assert unquote_filter_value(value)[0] == plain


@pytest.mark.parametrize("fields, key, quoted, plain", [
    (works_fields, "doi", '"10.1371/journal.pone.0266781"|"10.1371/journal.pone.0267149"',
     "10.1371/journal.pone.0266781|10.1371/journal.pone.0267149"),
    (works_fields, "primary_location.raw_type", '"journal article"|book', "journal article|book"),
    (works_fields, "primary_location.raw_type", '"journal article"|"book chapter"', "journal article|book chapter"),
    (works_fields, "primary_location.raw_type", '!"journal article"|book', "!journal article|book"),
    (works_fields, "locations.source.type", '"book series"|journal', "book series|journal"),
    (works_fields, "primary_location.landing_page_url", '"https://a.org/x"|"https://a.org/y"',
     "https://a.org/x|https://a.org/y"),
    (works_fields, "authorships.institutions.id", '"I136199984"|"I27837315"', "I136199984|I27837315"),
    (sources_fields, "display_name", '"Nature Communications"|"Scientific Reports"',
     "Nature Communications|Scientific Reports"),
    (awards_fields, "funder_scheme", '"Standard Grant"|"R01"', "Standard Grant|R01"),
    (awards_fields, "lead_investigator.affiliation.country", '"UNITED STATES"|Japan', "UNITED STATES|Japan"),
    (awards_fields, "lead_investigator.family_name", '"Smith"|"Jones"', "Smith|Jones"),  # TextTermField
])
def test_a_quoted_or_list_is_the_same_query_as_its_plain_values(fields, key, quoted, plain):
    assert _q(fields, key, quoted) == _q(fields, key, plain)


def test_quoted_or_operands_are_no_longer_literal_quotes():
    q = _q(works_fields, "primary_location.raw_type", '"journal article"|book')
    assert q["query"]["bool"]["filter"] == [{"terms": {"primary_location.raw_type.keyword": ["journal article", "book"]}}]


def test_search_filters_keep_their_quotes():
    q = str(_q(works_fields, "title.search", '"climate change"|"global warming"'))
    assert '"climate change"' in q


@pytest.mark.parametrize("value", ['"New York"|California', '"New York"|"California"'])
def test_url_parser_reads_quoted_or_operands(value):
    oqo = parse_url_to_oqo("works", filter_string=f"authorships.institutions.geo.region:{value}")
    assert [f.value for f in oqo.filter_rows[0].filters] == ["New York", "California"]


def test_url_parser_reads_negated_quoted_or():
    oqo = parse_url_to_oqo("works", filter_string='authorships.institutions.geo.region:!"New York"|California')
    branch = oqo.filter_rows[0]
    assert branch.is_negated and [f.value for f in branch.filters] == ["New York", "California"]


# ---------- 2. country filter values ----------

@pytest.mark.parametrize("fields, key, value, hint", [
    (institutions_fields, "country_code", "canada", "country_code:CA"),
    (institutions_fields, "country_code", "usa", "country_code:US"),
    (institutions_fields, "country_code", "DEU", "country_code:DE"),
    (institutions_fields, "country_code", "uk", "country_code:GB"),
    (works_fields, "institutions.country_code", "usa", "institutions.country_code:US"),
    (works_fields, "authorships.countries", "JPN", "authorships.countries:JP"),
    (works_fields, "authorships.institutions.country_code", "india", "authorships.institutions.country_code:IN"),
    (works_fields, "institutions.country_code", "us|china", "institutions.country_code:CN"),
    (works_fields, "institutions.country_code", '"united states"', "institutions.country_code:US"),
    (works_fields, "primary_location.source.country_code", "germany", "primary_location.source.country_code:DE"),
    (sources_fields, "country_code", "japan", "country_code:JP"),
])
def test_a_country_name_or_alpha3_names_the_code(fields, key, value, hint):
    msg = _error(fields, key, value)
    assert "is not a country code" in msg and hint in msg


def test_a_value_with_no_close_country_points_to_the_list():
    assert "https://api.openalex.org/countries" in _error(institutions_fields, "country_code", "zzqx9nonsense")


@pytest.mark.parametrize("value", [
    "US", "us", "US|CN", "!US", "!us|cn", "null", "!null", "countries/US",
    "https://openalex.org/countries/US", "XK", "EU", '"US"',
])
def test_country_codes_filter_as_before(value):
    assert _q(works_fields, "institutions.country_code", value)


def test_awards_free_text_country_is_not_a_code_filter():
    assert _q(awards_fields, "lead_investigator.affiliation.country", "UNITED STATES")


# ---------- 3. q= without group_by ----------

def _parse(url):
    with app.test_request_context(url):
        return parse_params(flask.request)


@pytest.mark.parametrize("url", ["/works?q=cancer", "/authors?q=smith&filter=works_count:>5", "/awards?q=nih"])
def test_q_without_group_by_points_to_search(url):
    with pytest.raises(APIQueryParamsError) as err:
        _parse(url)
    entity = url.split("?")[0].strip("/")
    assert f"/{entity}?search=" in str(err.value) and f"/autocomplete/{entity}?q=" in str(err.value)


@pytest.mark.parametrize("url", [
    "/works?group_by=type&q=art", "/works?group-by=type&q=art", "/works?group_bys=type,language&q=en",
    "/works?q=", "/works?q=''", "/works?search=cancer",
])
def test_q_with_group_by_or_empty_is_fine(url):
    assert _parse(url)


# ---------- 4. short ids on full-URL id filters ----------

@pytest.mark.parametrize("fields, key, short, url", [
    (awards_fields, "id", "G2966666733", "https://openalex.org/G2966666733"),
    (awards_fields, "id", "g2966666733", "https://openalex.org/G2966666733"),
    (works_fields, "authorships.affiliations.institution_ids", "I136199984", "https://openalex.org/I136199984"),
    (works_fields, "authorships.affiliations.institution_ids", "I136199984|I27837315",
     "https://openalex.org/I136199984|https://openalex.org/I27837315"),
    (works_fields, "authorships.affiliations.institution_ids", "!I136199984", "!https://openalex.org/I136199984"),
])
def test_a_short_id_is_its_url(fields, key, short, url):
    assert _q(fields, key, short) == _q(fields, key, url)
    assert "https://openalex.org/" in str(_q(fields, key, short))


def test_the_id_filters_keep_their_string_type():
    """/properties must not change (PROPERTIES_VERSION)."""
    assert awards_fields["id"].to_property() and awards_fields["id"].field_type == "string"
    assert works_fields["authorships.affiliations.institution_ids"].field_type == "string"


# ---------- 5. include_xpac ----------

@pytest.mark.parametrize("value, flag", [("true", True), ("True", True), ("TRUE", True), ('"true"', True),
                                         ("false", False), ("False", False), ("", False)])
def test_xpac_flag_values(value, flag):
    assert xpac_flag_value(value) is flag


@pytest.mark.parametrize("value", ["banana", "1", "yes", "all"])
def test_xpac_flag_other_values_are_a_400(value):
    with pytest.raises(APIQueryParamsError) as err:
        xpac_flag_value(value)
    assert "takes true or false" in str(err.value)


@pytest.mark.parametrize("url, controls", [
    ("/works?filter=authorships.institutions.id:I136199984,include_xpac:true", (True, True)),
    ("/works?filter=include-xpac:true", (True, True)),
    ("/works?filter=include_xpac:false", (False, True)),
    ("/works?include_xpac=true", (True, True)),
    ("/works?include_xpac=True", (True, True)),
    ("/works?include-xpac=true", (True, True)),
    ("/works?include_xpac=false", (False, True)),
    ("/works?filter=is_xpac:true", (False, False)),
    ("/works", (False, False)),
])
def test_xpac_controls(url, controls):
    with app.test_request_context(url):
        assert xpac_controls(flask.request) == controls


@pytest.mark.parametrize("url", ["/works?filter=include_xpac:banana", "/works?include_xpac=banana"])
def test_a_bad_xpac_value_is_a_400(url):
    with pytest.raises(APIQueryParamsError):
        _parse(url)


def test_include_xpac_filter_clause_is_not_a_filter():
    assert _q(works_fields, "include_xpac", "true") == Search().to_dict()
    with pytest.raises(APIQueryParamsError):
        _q(works_fields, "include_xpac", "banana")


def test_url_parser_reads_include_xpac_clause_as_the_corpus():
    oqo = parse_url_to_oqo("works", filter_string="authorships.institutions.id:I136199984,include_xpac:true")
    assert oqo.corpus == "all"
    assert [r.column_id for r in oqo.filter_rows] == ["authorships.institutions.id"]


# ---------- riders: null on dotted numbers, best_open_version, sort direction ----------

@pytest.mark.parametrize("fields, key", [
    (works_fields, "apc_list.value_usd"), (works_fields, "citation_normalized_percentile.value"),
    (sources_fields, "summary_stats.h_index"),
])
def test_null_on_a_dotted_number_names_the_dotted_field(fields, key):
    assert key in str(_q(fields, key, "!null")) and key in str(_q(fields, key, "null"))
    assert "__" not in str(_q(fields, key, "!null"))


def test_best_open_version_reads_the_best_open_copy():
    q = _q(works_fields, "best_open_version", "published")
    assert q["query"]["bool"]["filter"] == [{"terms": {"best_oa_location.version": ["publishedVersion"]}}]
    assert _q(works_fields, "best_open_version", "any|published") == _q(works_fields, "best_open_version", "any")
    neg = _q(works_fields, "best_open_version", "!acceptedOrPublished")
    assert neg["query"]["bool"]["filter"] == [{"bool": {"must_not": [
        {"terms": {"best_oa_location.version": ["acceptedVersion", "publishedVersion"]}}]}}]
    with pytest.raises(APIQueryParamsError):
        _q(works_fields, "best_open_version", "preprint")


@pytest.mark.parametrize("sort, direction", [("cited_by_count:DESC", "desc"), ("cited_by_count:Asc", "asc"),
                                             ("cited_by_count", "asc"), ("cited_by_count:desc", "desc")])
def test_sort_direction_any_case(sort, direction):
    assert _parse(f"/works?sort={sort}")["sort"] == {"cited_by_count": direction}


@pytest.mark.parametrize("sort", ["cited_by_count:descending", "cited_by_count:-1", "cited_by_count:"])
def test_other_sort_directions_are_a_400(sort):
    with pytest.raises(APIQueryParamsError) as err:
        _parse(f"/works?sort={sort}")
    assert "asc or desc" in str(err.value)
