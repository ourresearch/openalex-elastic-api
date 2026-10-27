"""When a `?` in a search is a wildcard and when it is a question mark (oxjob #1327).

Pure (no settings, no ES), so the OQL parser (query_translation/oql_lang.py) uses it too.

- Inside a word (`wom?n`, `wo??n`): a wildcard, as the docs promise.
- On its own (`garçons ? Une`, `"the Boat"?`) or inside a URL (`index.html?id=`): a
  question mark / separator.
- At the end of a word: a question mark when the search reads as text (two or more
  words and no AND/OR/NOT), as in a pasted title "Should we ditch impact factors?"; in a
  one-word or Boolean search (`psoriati?`, `psoriati? AND skin`) a wildcard (#570).
- At the start of a word (`?cycle`): left alone; the validators refuse a leading wildcard.

Before, every `?` counted as a wildcard, so a pasted title got HTTP 400 on the default
search and missed its paper on the exact one (numbers: oxjob #1327).
"""
import re

_QUESTION_MARK_RUN_RE = re.compile(r"\?+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_BOOLEAN_RE = re.compile(r"\b(?:AND|OR|NOT)\b")
# A word character, except Chinese/Japanese ideographs and kana: the tokenizer indexes those
# one character at a time, so a `?` beside one (`何が違う?(上)`) can never be a wildcard.
_WORD_CHAR_RE = re.compile(r"[^\W\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def reads_as_text(search_terms):
    """Two or more words and no Boolean operator: a title or a sentence, not a query."""
    return len(search_terms.split()) >= 2 and not _BOOLEAN_RE.search(search_terms)


def question_marks_as_punctuation(search_terms, as_text=None):
    """Drop each `?` that is a question mark (see the module doc). Dropping never joins two
    words: a `?` with a word character on both sides is a wildcard and stays.

    `as_text` says whether a word-final `?` is a question mark; by default it is
    `reads_as_text(search_terms)` (the OQL parser passes it for a run of bare words that
    it checks one word at a time). Idempotent.
    """
    if not search_terms or not isinstance(search_terms, str) or "?" not in search_terms:
        return search_terms
    if as_text is None:
        as_text = reads_as_text(search_terms)
    text = _URL_RE.sub(lambda m: m.group(0).replace("?", " "), search_terms)

    def _replace(m):
        start, end = m.start(), m.end()
        before = start > 0 and _WORD_CHAR_RE.match(text[start - 1])
        after = end < len(text) and _WORD_CHAR_RE.match(text[end])
        if after or (before and not as_text):
            return m.group(0)  # inside or at the start of a word; word-final in a query
        return ""

    # A search that was only `?` stays a non-empty blank, which matches nothing (like
    # `search=.`); an empty string would build match_all and return every record.
    return _QUESTION_MARK_RUN_RE.sub(_replace, text).strip() or " "
