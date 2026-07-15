"""Friendly country display names (oxjob #616).

The canonical country display_names are the friendly short forms (South
Korea, Ivory Coast, Taiwan) — walden's openalex.common.countries feeds the
countries-v2 index / GET /countries, and config/countries.yaml mirrors it
(enforced by scripts/check_vocab_parity.py). The iso3166 package's official
ISO-3166 names (Korea, Republic of / Côte d'Ivoire / Taiwan, Province of
China) are kept only as a lookup fallback and as name->code aliases, so
anything that matched before the rename still matches.

The registry import is lazy: core.entities pulls in the whole combined
config, and importing it at module load from low-level helpers has
deadlocked before (see core.shared_view's query_translation note).
"""
import iso3166

_code_to_name = None
_name_to_code = None


def _friendly_table():
    global _code_to_name
    if _code_to_name is None:
        table = {}
        try:
            from core.entities import get_entity_type

            ent = get_entity_type("countries")
            for row in (ent.values or []) if ent else []:
                rid = str(row.get("id", ""))
                code = rid.split("/")[-1].upper()
                name = row.get("display_name")
                if code and name:
                    table[code] = name
        except Exception:  # pragma: no cover - registry unavailable/corrupt
            table = {}
        _code_to_name = table
    return _code_to_name


def get_country_name(country_code, default=None):
    """Friendly display name for an alpha-2 code; ISO official name if the
    code isn't in the registry; `default` if it isn't a country at all."""
    if not country_code:
        return default
    name = _friendly_table().get(country_code.upper())
    if name:
        return name
    try:
        country = iso3166.countries.get(country_code.lower())
    except KeyError:
        country = None
    return country.name if country else default


def countries_by_name():
    """{UPPERCASE name: alpha-2} over friendly names PLUS the ISO official
    names as aliases — for name->code matchers (group_by q=, autocomplete)."""
    global _name_to_code
    if _name_to_code is None:
        table = {
            name.upper(): country.alpha2
            for name, country in iso3166.countries_by_name.items()
        }
        table.update(
            {name.upper(): code for code, name in _friendly_table().items()}
        )
        _name_to_code = table
    return _name_to_code
