"""A country filter value must be a country code (oxjob #2140).

`institutions.country_code:usa`, `country_code:canada` and `authorships.countries:JPN` each answered
a count of 0 with no message (~2-3K requests a day): the index holds two-letter ISO 3166-1 codes.
Now any other value answers a JSON 400 that names the code to use, as a works `type` filter does
(oxjob #1836). Values the index holds that aren't ISO codes (Kosovo's XK, a few historic codes)
stay valid, so no filter that found records before finds none now.

Only values a user typed are checked (core/filter.py). Collections (`col_...`) resolve elsewhere.
"""
from functools import lru_cache

import pycountry

from core.exceptions import APIQueryParamsError
from core.fields import JoinField, TermField
from core.work_type_values import _operands

# Codes the live index holds beyond ISO 3166-1 alpha-2 (every country group_by paged, 10 Nov 2026):
# Kosovo; the EU (funders); historic Serbia and Montenegro / Czechoslovakia, East Germany, USSR
# (sources, publishers); and three alpha-3 codes some publishers carry.
EXTRA_CODES = {"XK", "EU", "CS", "DD", "SU", "CSK", "ESH", "SUN"}

# Common names for a code that pycountry's lookup doesn't know.
ALIASES = {"UK": "GB", "ENGLAND": "GB", "SCOTLAND": "GB", "WALES": "GB", "BRITAIN": "GB",
           "GREAT BRITAIN": "GB", "EL": "GR", "KOSOVO": "XK", "RUSSIA": "RU", "SOUTH KOREA": "KR",
           "KOREA": "KR", "NORTH KOREA": "KP", "IRAN": "IR", "VIETNAM": "VN", "TAIWAN": "TW",
           "AMERICA": "US", "UNITED STATES OF AMERICA": "US"}

# The last segment of a filter that takes country codes (country_code, country_codes, countries).
_COUNTRY_KEYS = ("country_code", "country_codes", "countries")


@lru_cache(maxsize=1)
def country_codes():
    return frozenset(c.alpha_2 for c in pycountry.countries) | EXTRA_CODES


def is_country_filter(field):
    return isinstance(field, (TermField, JoinField)) and field.param.split(".")[-1] in _COUNTRY_KEYS


def _code(value):
    return TermField._strip_openalex_prefix(value.strip(), "countries/").upper()


def suggested_code(value):
    """The country code someone who typed `value` most likely wants, or None."""
    code = _code(value)
    if code in ALIASES:
        return ALIASES[code]
    try:
        return pycountry.countries.lookup(value.strip()).alpha_2  # alpha-3, number, or English name
    except LookupError:
        pass
    try:
        return pycountry.countries.search_fuzzy(value.strip())[0].alpha_2
    except LookupError:
        return None


def unknown_country_message(param, value):
    """None when `value` is a country code (or null); else the sentence that says what to use."""
    code = _code(value)
    if not code or code == "NULL" or code in country_codes():
        return None
    use = suggested_code(value)
    if use:
        name = pycountry.countries.get(alpha_2=use)
        named = f" ({name.name})" if name else ""
        hint = f"Use {param}:{use}{named}."
    else:
        hint = "For example US, GB or CN (the list: https://api.openalex.org/countries)."
    return (f"'{value}' is not a country code: {param} takes two-letter ISO 3166-1 country codes. "
            f"{hint}")


def check_country_filter(field, value, is_quoted=False):
    """Raise APIQueryParamsError (a JSON 400) when a country filter names something that isn't a
    country code. `value` is the filter value after quote handling, as core.filter routes it."""
    if not is_country_filter(field):
        return
    for operand in _operands(value, is_quoted):
        message = operand and unknown_country_message(field.param, operand)
        if message:
            raise APIQueryParamsError(message)
