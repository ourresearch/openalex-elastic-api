"""When a `?` or `*` in a search is a wildcard and when it is punctuation (oxjob #1327).

Pure (no settings, no ES), so the OQL parser (query_translation/oql_lang.py) uses it too.

`?`:
- Inside a word (`wom?n`, `wo??n`): a wildcard, as the docs promise.
- At the end of a word: a wildcard in a one-word search (`psoriati?`, #570); in any longer
  search a question mark, as in a pasted title "Should we ditch impact factors?".
- On its own (`garçons ? Une`, `"the Boat"?`), inside a URL (`index.html?id=`), or beside
  Chinese/Japanese text: punctuation.
- At the start of a word (`?cycle`): left alone; the validators refuse a leading wildcard.
`*` on its own (a footnote mark: `Yun Hao 1, * ,`) is punctuation; every other `*` is left
to the wildcard rules (`machin*`, `chem*stry`).

Before, every `?` and `*` counted as a wildcard, so a pasted title got HTTP 400 on the
default search and missed its paper on the exact one (numbers: oxjob #1327).
"""
import re

_QUESTION_MARK_RUN_RE = re.compile(r"\?+")
_LONE_STAR_RE = re.compile(r"(?<!\S)\*+(?!\S)")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# A word character, except Chinese/Japanese ideographs and kana: the tokenizer indexes those
# one character at a time, so a `?` beside one (`何が違う?(上)`) can never be a wildcard.
_WORD_CHAR_RE = re.compile(r"[^\W぀-ヿ㐀-䶿一-鿿豈-﫿]")


def wildcard_chars_as_punctuation(search_terms, as_text=None):
    """Drop each `?` or `*` that is punctuation (see the module doc). Dropping never joins
    two words: a `?` with a word character on both sides is a wildcard and stays.

    `as_text` says whether a word-final `?` is a question mark; by default it is when the
    search has two or more words (the OQL parser passes it for a run of bare words that it
    checks one word at a time). Idempotent.
    """
    if not search_terms or not isinstance(search_terms, str):
        return search_terms
    if "?" not in search_terms and "*" not in search_terms:
        return search_terms
    if as_text is None:
        as_text = len(search_terms.split()) >= 2
    text = _LONE_STAR_RE.sub("", search_terms)
    text = _URL_RE.sub(lambda m: m.group(0).replace("?", " "), text)

    def _replace(m):
        start, end = m.start(), m.end()
        before = start > 0 and _WORD_CHAR_RE.match(text[start - 1])
        after = end < len(text) and _WORD_CHAR_RE.match(text[end])
        if after or (before and not as_text):
            return m.group(0)  # inside or at the start of a word; word-final in one word
        return ""

    # A search that was only punctuation stays a non-empty blank, which matches nothing
    # (like `search=.`); an empty string would build match_all and return every record.
    return _QUESTION_MARK_RUN_RE.sub(_replace, text).strip() or " "
