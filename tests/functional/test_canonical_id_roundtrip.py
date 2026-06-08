"""Canonical OpenAlex id filter round-trip (#275).

Every entity API returns a canonical ``id`` URL (e.g. ``/sdgs/4`` returns
``https://openalex.org/sdgs/4``). Users copy that URL and paste it as a filter
value. For several params the canonical form used to match ZERO docs because the
normalization stripped the entity prefix as a substring (``.replace("sdgs/","")``)
while leaving the ``https://openalex.org`` host on, so a different (un-normalized)
value reached Elasticsearch.

These tests assert the fix at the unit level (no ES): for each affected param,
``TermField._get_formatted_value()`` and ``TermField.build_query()`` produce the
SAME result for the canonical URL as for the short/bare form that already works.

Indexed ground-truth (verified live against prod 2026-06-07):
  - sustainable_development_goals.id -> https://metadata.un.org/sdg/N
  - language / type / source.type / country -> bare code
  - domain.id / field.id / subfield.id -> full https://openalex.org/<kind>/N URL

Run offline:
  PYTHONPATH=. venv/bin/python -m pytest \
      tests/functional/test_canonical_id_roundtrip.py --noconftest -q
"""

import pytest

from core.fields import TermField


def _field(param, value, **kwargs):
    f = TermField(param=param, **kwargs)
    f.value = value
    return f


def _formatted(param, value, **kwargs):
    return _field(param, value, **kwargs)._get_formatted_value()


def _query_dict(param, value, **kwargs):
    # build_query() mutates self.value, so always use a fresh field.
    return _field(param, value, **kwargs).build_query().to_dict()


# param, short form (already works), canonical openalex.org URL, expected indexed value
ROUNDTRIP_CASES = [
    (
        "sustainable_development_goals.id",
        "4",
        "https://openalex.org/sdgs/4",
        "https://metadata.un.org/sdg/4",
    ),
    ("language", "en", "https://openalex.org/languages/en", "en"),
    ("type", "article", "https://openalex.org/types/article", "article"),
    (
        "primary_location.source.type",
        "journal",
        "https://openalex.org/source-types/journal",
        "journal",
    ),
    (
        "authorships.countries",
        "US",
        "https://openalex.org/countries/US",
        "US",
    ),
]


@pytest.mark.parametrize("param,short,canonical,expected", ROUNDTRIP_CASES)
def test_formatted_value_matches_short_form(param, short, canonical, expected):
    """The canonical URL normalizes to the same indexed value as the short form."""
    assert _formatted(param, expected) == expected  # already-indexed form is stable
    assert _formatted(param, short) == expected
    assert _formatted(param, canonical) == expected


@pytest.mark.parametrize("param,short,canonical,expected", ROUNDTRIP_CASES)
def test_build_query_matches_short_form(param, short, canonical, expected):
    """The canonical URL builds the identical ES query as the short form."""
    assert _query_dict(param, canonical) == _query_dict(param, short)


# domain/field/subfield index the FULL openalex URL and build_query ORs the full
# URL with the bare code, so the canonical URL must reduce to the bare code (then
# the existing OR matches). _get_formatted_value already returns the full URL.
PREFIXED_NUMERIC_CASES = [
    ("primary_topic.domain.id", "2", "https://openalex.org/domains/2", "domains"),
    ("primary_topic.field.id", "22", "https://openalex.org/fields/22", "fields"),
    (
        "primary_topic.subfield.id",
        "2207",
        "https://openalex.org/subfields/2207",
        "subfields",
    ),
]


@pytest.mark.parametrize("param,short,canonical,kind", PREFIXED_NUMERIC_CASES)
def test_domain_family_build_query_roundtrips(param, short, canonical, kind):
    assert _query_dict(param, canonical) == _query_dict(param, short)


@pytest.mark.parametrize("param,short,canonical,kind", PREFIXED_NUMERIC_CASES)
def test_domain_family_formatted_value(param, short, canonical, kind):
    full = f"https://openalex.org/{kind}/{short}"
    assert _formatted(param, short) == full
    assert _formatted(param, f"{kind}/{short}") == full
    assert _formatted(param, canonical) == full


# --- Negation (#275 follow-up): a negated canonical URL must build the same query
# as the negated short form, and must actually be a negation (bool.must_not). The
# old behavior mangled the value so `!canonical` excluded nothing (matched all). ---
ALL_NEG_CASES = ROUNDTRIP_CASES + [
    (p, s, c, e) for (p, s, c, e) in PREFIXED_NUMERIC_CASES
] + [
    (
        "authorships.institutions.country_code",
        "US",
        "https://openalex.org/countries/US",
        "US",
    ),
    (
        "authorships.institutions.type",
        "funder",
        "https://openalex.org/institution-types/funder",
        "funder",
    ),
]


@pytest.mark.parametrize("param,short,canonical,_x", ALL_NEG_CASES)
def test_negated_canonical_matches_negated_short(param, short, canonical, _x):
    assert _query_dict(param, "!" + canonical) == _query_dict(param, "!" + short)


@pytest.mark.parametrize("param,short,canonical,_x", ALL_NEG_CASES)
def test_negated_is_actually_a_negation(param, short, canonical, _x):
    d = _query_dict(param, "!" + canonical)
    assert "must_not" in d.get("bool", {}), d


def test_negation_marker_preserved_by_normalizer():
    f = TermField(param="primary_topic.domain.id")
    assert f._normalize_term_value("!https://openalex.org/domains/2") == "!2"
    assert f._normalize_term_value("https://openalex.org/domains/2") == "2"
    # !null is a sentinel, never normalized
    assert f._normalize_term_value("!null") == "!null"


# Regression guard: the forms that already worked must keep working unchanged.
def test_existing_sdg_forms_unchanged():
    indexed = "https://metadata.un.org/sdg/4"
    for v in ("4", "sdgs/4", "https://metadata.un.org/sdg/4"):
        assert _formatted("sustainable_development_goals.id", v) == indexed


def test_keywords_still_roundtrips():
    indexed = "https://openalex.org/keywords/cardiology"
    for v in ("cardiology", "keywords/cardiology", indexed):
        assert _formatted("keywords.id", v) == indexed


def test_language_is_lowercased():
    # _get_formatted_value now lowercases language to match build_query and the
    # __lower indexed field (previously a dead duplicate branch tried to do this).
    assert _formatted("language", "EN") == "en"
    assert _formatted("language", "https://openalex.org/languages/EN") == "en"


def test_strip_helper_strips_host_then_prefix():
    assert TermField._strip_openalex_prefix(
        "https://openalex.org/languages/en", "languages/"
    ) == "en"
    assert TermField._strip_openalex_prefix("languages/en", "languages/") == "en"
    assert TermField._strip_openalex_prefix("en", "languages/") == "en"
    # multiple candidate prefixes: first match wins, others ignored
    assert TermField._strip_openalex_prefix(
        "https://openalex.org/types/article",
        "work-types/",
        "types/",
    ) == "article"


def test_sdg_helper():
    assert TermField._normalize_sdg_value("4") == "https://metadata.un.org/sdg/4"
    assert TermField._normalize_sdg_value("sdgs/17") == "https://metadata.un.org/sdg/17"
    assert (
        TermField._normalize_sdg_value("https://openalex.org/sdgs/7")
        == "https://metadata.un.org/sdg/7"
    )
    assert (
        TermField._normalize_sdg_value("https://metadata.un.org/sdg/4")
        == "https://metadata.un.org/sdg/4"
    )
