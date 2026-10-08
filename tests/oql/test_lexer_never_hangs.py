"""The lexer always moves forward (oxjob #1555 found it looping forever on a stray `]`,
growing memory until the worker died). Every input either lexes or raises an OQLError,
quickly."""
import signal

import pytest

from query_translation.diagnostics import OQLError
from query_translation.oql_lang import lex, parse


@pytest.fixture(autouse=True)
def _two_second_limit():
    def on_alarm(*_):
        raise TimeoutError("the lexer or parser looped")
    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(2)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.mark.parametrize("q,code", [
    ("works where title has kelp]", "OQL_UNMATCHED_BRACKET"),
    ("works where year is ([[start year]])", "OQL_UNMATCHED_BRACKET"),
    ("]", "OQL_UNMATCHED_BRACKET"),
    ("works where title has (a]b)", "OQL_UNMATCHED_BRACKET"),
])
def test_stray_bracket_is_an_error_not_a_hang(q, code):
    with pytest.raises(OQLError) as e:
        parse(q)
    assert e.value.code == code


def test_every_ascii_character_lexes_or_errors():
    for c in map(chr, range(32, 127)):
        for q in (c, f"works where title has {c}", f"works where title has a{c}b", c * 3):
            try:
                lex(q)
            except OQLError:
                pass


def test_brackets_in_quotes_and_links_still_lex():
    assert parse('works where title has "a]b"') is not None
    assert parse("works where institution is [MIT](I63966007)") is not None
