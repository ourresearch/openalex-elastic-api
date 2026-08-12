"""Top-level `corpus=` REST param (oxjob #763).

The corpus decision itself is a pure function (`resolve_corpus_default_filters`)
so the allow/deny matrix is unit-tested here without a request or ES. The
x_query surfaces (url_parser corpus kwarg, url_renderer `corpus=` component)
are covered alongside since #763 is what gave a non-core corpus a classic URL
form at all.
"""
import pytest

from core.exceptions import APIQueryParamsError
from works.views import resolve_corpus_default_filters


def _resolve(corpus=None, xpac_param_present=False, xpac_in_filter=False,
             include_xpac=False):
    return resolve_corpus_default_filters(
        corpus=corpus,
        xpac_param_present=xpac_param_present,
        xpac_in_filter=xpac_in_filter,
        include_xpac=include_xpac,
    )


# --- legacy behavior (corpus absent) is unchanged -------------------------

def test_no_controls_defaults_to_core():
    assert _resolve() == [{"is_xpac": "false"}]


def test_legacy_include_xpac_suppresses_default():
    assert _resolve(xpac_param_present=True, include_xpac=True) is None


def test_legacy_is_xpac_filter_suppresses_default():
    assert _resolve(xpac_in_filter=True) is None


def test_legacy_include_xpac_false_keeps_default():
    # ?include_xpac=false (or junk) present but not true: default stays.
    assert _resolve(xpac_param_present=True, include_xpac=False) == [
        {"is_xpac": "false"}
    ]


# --- the new corpus= mapping ----------------------------------------------

def test_corpus_core_pins_core():
    assert _resolve(corpus="core") == [{"is_xpac": "false"}]


def test_corpus_expansion_selects_expansion_only():
    assert _resolve(corpus="expansion") == [{"is_xpac": "true"}]


def test_corpus_all_lifts_constraint():
    assert _resolve(corpus="all") is None


def test_corpus_value_is_case_and_whitespace_insensitive():
    assert _resolve(corpus="  Expansion ") == [{"is_xpac": "true"}]


def test_corpus_invalid_value_raises_with_valid_values_listed():
    with pytest.raises(APIQueryParamsError, match="core, expansion, all"):
        _resolve(corpus="banana")


def test_corpus_empty_value_raises():
    with pytest.raises(APIQueryParamsError, match="core, expansion, all"):
        _resolve(corpus="")


# --- mutual exclusion: corpus never combines with the legacy controls ------

@pytest.mark.parametrize("corpus", ["core", "expansion", "all", "banana"])
def test_corpus_plus_include_xpac_param_always_400s(corpus):
    # Even agreeing combos (corpus=all + include_xpac=true) are rejected —
    # mixing the vocabularies is the footgun, not the disagreement.
    with pytest.raises(APIQueryParamsError, match="deprecated legacy"):
        _resolve(corpus=corpus, xpac_param_present=True, include_xpac=True)


def test_corpus_plus_include_xpac_false_still_400s():
    with pytest.raises(APIQueryParamsError, match="cannot be combined"):
        _resolve(corpus="all", xpac_param_present=True, include_xpac=False)


def test_corpus_plus_is_xpac_filter_400s():
    with pytest.raises(APIQueryParamsError, match="cannot be combined"):
        _resolve(corpus="expansion", xpac_in_filter=True)


def test_conflict_message_names_the_replacement():
    with pytest.raises(APIQueryParamsError, match="corpus=core"):
        _resolve(corpus="all", xpac_param_present=True, include_xpac=True)


# --- x_query surfaces: URL parse + render ----------------------------------

def test_url_parser_accepts_corpus_kwarg():
    from query_translation.url_parser import parse_url_to_oqo

    oqo = parse_url_to_oqo(entity_type="works", corpus="expansion")
    assert oqo.corpus == "expansion"


def test_url_parser_corpus_default_and_include_xpac_fallback():
    from query_translation.url_parser import parse_url_to_oqo

    assert parse_url_to_oqo(entity_type="works").corpus == "core"
    assert parse_url_to_oqo(entity_type="works", include_xpac=True).corpus == "all"
    # corpus (when present) beats the legacy flag — the REST view 400s the
    # combination, so this ordering only matters for direct callers.
    assert (
        parse_url_to_oqo(entity_type="works", corpus="expansion",
                         include_xpac=True).corpus
        == "expansion"
    )


def test_url_renderer_emits_corpus_component():
    from query_translation.oqo import OQO
    from query_translation.url_renderer import render_oqo_to_url

    components = render_oqo_to_url(OQO(get_rows="works", corpus="expansion"))
    assert components["corpus"] == "expansion"
    # core is the default and is omitted, like every other default.
    assert render_oqo_to_url(OQO(get_rows="works"))["corpus"] is None
    assert (
        render_oqo_to_url(OQO(get_rows="works", corpus="core"))["corpus"] is None
    )


def test_corpus_url_round_trips():
    from query_translation.oqo import OQO
    from query_translation.url_parser import parse_url_to_oqo
    from query_translation.url_renderer import render_oqo_to_url

    for corpus in ("expansion", "all"):
        rendered = render_oqo_to_url(OQO(get_rows="works", corpus=corpus))
        reparsed = parse_url_to_oqo(entity_type="works",
                                    corpus=rendered["corpus"])
        assert reparsed.corpus == corpus
