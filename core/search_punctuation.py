"""When a `?` or `*` in a search is a wildcard and when it is punctuation (oxjob #1327).

Pure (no settings, no ES), so the OQL parser (query_translation/oql_lang.py) uses it too.

`?`:
- Inside a word (`wom?n`, `wo??n`): a wildcard, as the docs promise.
- At the end of a word: a wildcard in a one-word search (`psoriati?`, #570); in any longer
  search a question mark, as in a pasted title "Should we ditch impact factors?".
- On its own (`garçons ? Une`, `"the Boat"?`), inside a URL (`index.html?id=`), or beside
  Chinese/Japanese text: punctuation.
- At the start of a word (`?cycle`): left alone; the validators refuse a leading wildcard.
`*` on its own (a footnote mark: `Yun Hao 1, * ,`) is punctuation, also beside a quote
(`"Prof. *"`, `"* cancer"`: ES answered those HTTP 500, "Automaton [*] expanded to too many
terms", oxjob #1889); every other `*` is left to the wildcard rules (`machin*`, `chem*stry`).

Before, every `?` and `*` counted as a wildcard, so a pasted title got HTTP 400 on the
default search and missed its paper on the exact one (numbers: oxjob #1327).

Pasted text (oxjob #2201). The works search doors pass `pasted="stemmed"` or `"exact"`, and a
search of two or more words that is not Boolean (no AND / OR / NOT beside lower-case text)
is then read as pasted text, outside quoted phrases:
- A `*` no wildcard rule accepts is punctuation on both doors: at the start of a word
  (`*On Bullshit*`, `**Mamba`), after fewer than 3 word characters (`A*`, `C*-algebras`,
  `Wang J*,`), doubled or repeated in one word (`negociaciones**.`, `the*potential*health`).
  So is a `?` that starts a word (`?Qu? es`).
- A `*` that looks like truncation (`Daylight*`, `bathymetr*`) and a `?` inside a word
  (`Fran?ois`) are punctuation only on the stemmed door, where they could only answer
  HTTP 400, and only in a search of LONG_TEXT_WORDS or more words in which under a third of
  the words are truncated: a title with a footnote mark, not `child* obes* school* interven*`.
  A search with a word that starts with `*` (Markdown emphasis) is read this way at any length.
Shorter searches and Boolean ones keep the 400 and its advice (`pest* fruit quality`,
`parent* OR mother*`). Traffic, 12-13 Nov 2026: about 9K works searches a day answered 400
for a `*` or `?`; pasted titles and Markdown references were most of them.
"""
import re

_QUESTION_MARK_RUN_RE = re.compile(r"\?+")
# A run of `*` with only spaces, quotes or the ends of the text beside it.
_LONE_STAR_RE = re.compile(r'(?<![^\s"])\*+(?![^\s"])')
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# A word character, except Chinese/Japanese ideographs and kana: the tokenizer indexes those
# one character at a time, so a `?` beside one (`何が違う?(上)`) can never be a wildcard.
_WORD_CHAR_RE = re.compile(r"[^\W぀-ヿ㐀-䶿一-鿿豈-﫿]")

LONG_TEXT_WORDS = 4
_BOOLEAN_WORD_RE = re.compile(r"(?<![^\s(])(?:AND|OR|NOT)(?![^\s)])")
_QUOTED_PHRASE_RE = re.compile(r'"[^"]*"(?:~\d+)?')
_STAR_RUN_RE = re.compile(r"\*+")
# One `*`, after 3 or more word characters: the shape the wildcard validators accept.
_TRUNCATION_RE = re.compile(r"""^[^*]*\w{3}\*[\w)\]}.,;:!'"-]*$""")
_INNER_QUESTION_MARK_RE = re.compile(r"(?<=\w)\?+(?=\w)")

# The works search columns with a stemmed and a no-stem (`.exact`) form (core/search.py
# WILDCARD_REQUIRES_EXACT; kept here so this module stays pure).
_STEMMED_WORKS_SEARCH_FIELDS = frozenset((
    "default.search", "title.search", "abstract.search", "fulltext.search", "display_name.search",
    "title_and_abstract.search", "title_abstract_keywords.search",
))


def pasted_door(field, entity):
    """`pasted` for wildcard_chars_as_punctuation: "stemmed" / "exact" for a works search
    column (`title.search`, `title.search.exact`), None for any other field or entity."""
    if not entity or not str(entity).lower().startswith("work"):
        return None
    if field in _STEMMED_WORKS_SEARCH_FIELDS:
        return "stemmed"
    if field.endswith(".exact") and field[: -len(".exact")] in _STEMMED_WORKS_SEARCH_FIELDS:
        return "exact"
    return None


def _is_boolean(text):
    """AND / OR / NOT as operators: upper-case words in text that is not all upper-case
    (`SITING TOXIC WASTE ... IN CANADA AND THE UNITED STATES*` is a title)."""
    return bool(_BOOLEAN_WORD_RE.search(text)) and any(c.islower() for c in text)


def _drop_stars(word):
    """The word without its `*`; a `*` between two word characters becomes a space."""
    def _one(m):
        between = (m.start() > 0 and m.end() < len(word)
                   and re.match(r"\w", word[m.start() - 1]) and re.match(r"\w", word[m.end()]))
        return " " if between else ""
    return _STAR_RUN_RE.sub(_one, word)


def _pasted_text(text, stemmed):
    """The pasted-text reading of a multi-word, non-Boolean search (see the module doc)."""
    if ("*" not in text and "?" not in text) or len(text.split()) < 2 or _is_boolean(text):
        return text
    # Quoted phrases keep their wildcards (`"smart phone*"~3` is an intervals query).
    pieces, pos = [], 0
    for m in _QUOTED_PHRASE_RE.finditer(text):
        pieces.append((text[pos:m.start()], False))
        pieces.append((m.group(0), True))
        pos = m.end()
    pieces.append((text[pos:], False))
    words = [w for piece, quoted in pieces if not quoted for w in piece.split()]
    truncations = [w for w in words if _TRUNCATION_RE.match(w)]
    n_words = len(text.split())
    # A word that starts with `*` is Markdown emphasis (`*On Bullshit*`): its closing `*` is too.
    markdown = any(w.startswith("*") for w in words)
    long_text = stemmed and (markdown or (n_words >= LONG_TEXT_WORDS and 3 * len(truncations) < n_words))

    def _word(m):
        w = m.group(0)
        if "*" in w and (long_text or not _TRUNCATION_RE.match(w)):
            w = _drop_stars(w)
        if "?" in w:
            w = w.lstrip("?") or w
            if long_text:
                w = _INNER_QUESTION_MARK_RE.sub(" ", w)
        return w

    return "".join(piece if quoted else re.sub(r"\S+", _word, piece) for piece, quoted in pieces)



def wildcard_chars_as_punctuation(search_terms, as_text=None, pasted=None):
    """Drop each `?` or `*` that is punctuation (see the module doc). Dropping never joins
    two words: a `?` with a word character on both sides is a wildcard and stays.

    `as_text` says whether a word-final `?` is a question mark; by default it is when the
    search has two or more words (the OQL parser passes it for a run of bare words that it
    checks one word at a time). `pasted` ("stemmed" or "exact", from a works search door)
    also reads a multi-word search as pasted text (module doc, oxjob #2201). Idempotent.
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
    text = _QUESTION_MARK_RUN_RE.sub(_replace, text)
    if pasted:
        text = _pasted_text(text, stemmed=(pasted == "stemmed"))
    return text.strip() or " "
