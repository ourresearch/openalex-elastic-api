"""A country filter value must be a country code (oxjob #2140).

`institutions.country_code:usa` and `country_code:canada` answered a count of 0 with no message:
the index holds two-letter ISO 3166-1 codes. Any other value now answers a JSON 400 that names the
code to use, as a works `type` filter does (oxjob #1836). Codes the index holds that aren't ISO
codes stay valid, so no filter that found records before finds none now.

Only values a user typed are checked (core/filter.py). Collections (`col_...`) resolve elsewhere.
"""
from functools import lru_cache

import pycountry

from core.country_names import countries_by_name, get_country_name
from core.exceptions import APIQueryParamsError
from core.fields import JoinField, TermField
from core.quoted_values import filter_operands

# Codes the live index holds beyond ISO 3166-1 alpha-2 (every country group_by paged, 10 Nov 2026):
# Kosovo, the EU (funders), historic codes and three alpha-3 codes (sources, publishers).
EXTRA_CODES = {"XK", "EU", "CS", "DD", "SU", "CSK", "ESH", "SUN"}

# Names neither the countries registry nor pycountry resolves.
ALIASES = {"UK": "GB", "EL": "GR", "KOREA": "KR", "AMERICA": "US"}

# The last segment of a filter that takes country codes.
_COUNTRY_KEYS = ("country_code", "country_codes", "countries")


@lru_cache(maxsize=1)
def country_codes():
    return frozenset(c.alpha_2 for c in pycountry.countries) | EXTRA_CODES


def is_country_filter(field):
    return isinstance(field, (TermField, JoinField)) and field.param.split(".")[-1] in _COUNTRY_KEYS


def suggested_code(value):
    """The country code someone who typed `value` most likely wants, or None."""
    name = value.strip()
    code = ALIASES.get(name.upper()) or countries_by_name().get(name.upper())
    if code:
        return code
    try:
        return pycountry.countries.lookup(name).alpha_2  # alpha-3, number, or ISO name
    except LookupError:
        pass
    try:
        return pycountry.countries.search_fuzzy(name)[0].alpha_2
    except LookupError:
        return None


def unknown_country_message(param, value):
    """None when `value` is a country code (or null); else the sentence that says what to use."""
    code = TermField._strip_openalex_prefix(value.strip(), "countries/").upper()
    if not code or code == "NULL" or code in country_codes():
        return None
    use = suggested_code(value)
    if use:
        hint = f"Use {param}:{use} ({get_country_name(use, use)})."
    else:
        hint = "For example US, GB or CN (the list: https://api.openalex.org/countries)."
    return (f"'{value}' is not a country code: {param} takes two-letter ISO 3166-1 country codes. "
            f"{hint}")


def check_country_filter(field, value, is_quoted=False):
    """Raise APIQueryParamsError (a JSON 400) when a country filter names something that isn't a
    country code. `value` is the filter value after quote handling, as core.filter routes it."""
    if not is_country_filter(field):
        return
    for operand in filter_operands(value, is_quoted):
        message = unknown_country_message(field.param, operand)
        if message:
            raise APIQueryParamsError(message)
