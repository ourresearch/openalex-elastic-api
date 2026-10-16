"""Awards `recipients.id` / `recipients.ror` filters (oxjob #1570).

awards-v4 maps `recipients_full.id` and `recipients_full.ror` as keyword and the
nightly stores the full forms (https://openalex.org/I…, https://ror.org/…), so
both filters must reduce the short and full value forms to the same term.
No ES needed: these assert on the queries the fields build.
"""
import copy

import pytest

from awards.fields import fields_dict as awards_fields

ID_FULL = "https://openalex.org/I4210112663"
ROR_FULL = "https://ror.org/0259fwx54"


def _field(param, value):
    f = copy.deepcopy(awards_fields[param])
    f.value = value
    return f


@pytest.mark.parametrize("value", ["I4210112663", "i4210112663", ID_FULL])
def test_recipients_id_term(value):
    q = _field("recipients.id", value).build_query().to_dict()
    assert q == {"term": {"recipients_full.id": ID_FULL}}, q


@pytest.mark.parametrize("value", ["0259fwx54", ROR_FULL])
def test_recipients_ror_term(value):
    q = _field("recipients.ror", value).build_query().to_dict()
    assert q == {"term": {"recipients_full.ror": ROR_FULL}}, q


@pytest.mark.parametrize("value", ["!0259fwx54", "!" + ROR_FULL])
def test_recipients_ror_negated(value):
    q = _field("recipients.ror", value).build_query().to_dict()
    assert q == {"bool": {"must_not": [{"term": {"recipients_full.ror": ROR_FULL}}]}}, q


@pytest.mark.parametrize("value", ["!I4210112663", "!" + ID_FULL])
def test_recipients_id_negated(value):
    q = _field("recipients.id", value).build_query().to_dict()
    assert q == {"bool": {"must_not": [{"term": {"recipients_full.id": ID_FULL}}]}}, q


def test_recipients_or_values_formatted():
    f = _field("recipients.ror", None)
    for given in ("0259fwx54", ROR_FULL):
        f.value = given
        assert f._get_formatted_value() == ROR_FULL, given
    f = _field("recipients.id", None)
    for given in ("I4210112663", ID_FULL):
        f.value = given
        assert f._get_formatted_value() == ID_FULL, given


def test_recipients_null():
    q = _field("recipients.ror", "!null").build_query().to_dict()
    assert q == {"exists": {"field": "recipients_full.ror"}}, q
