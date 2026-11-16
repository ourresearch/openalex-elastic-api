"""Boolean precedence for search strings: NOT, then AND, then OR (oxjob #1050).

The docs (help.openalex.org OQL spec, "Booleans and precedence") and the API's own
echo (`meta.x_query.oql`, built by query_translation/url_parser.py) read a search
string the way boolean algebra, Web of Science and most databases do: `NOT` binds
tightest, then `AND` (written, or two operands side by side), then `OR`. So
`a AND b OR c` is `(a AND b) OR c`, `a OR b AND c` is `a OR (b AND c)` and
`climate change OR warming` is `(climate change) OR warming`.

ES `query_string` runs Lucene's classic parser instead, which has no precedence: each
operator flips the required/optional flag of the term before it. With
`default_operator=AND`, `a AND b AND c AND d OR e` becomes `+a +b +c d e`, so `d` and
`e` only change the ranking: ZD 4409's `"life" AND "cycle" AND "sustainability" AND
"asdsaddsadasd" OR "lcsdasasdasda"` returned the 92,672 works of `"life" AND "cycle"
AND "sustainability"` while the echo said it ran `("lcsdasasdasda" OR (...))`.
`kelp OR urchin AND otter` returned 16 works (`+urchin +otter`, kelp dropped).

explicit_boolean_precedence() writes the grouping into the string with parentheses,
so Lucene runs what the echo says. It only inserts `(` and `)`; every other character
stays where it was. Text it can't read for sure (an unbalanced quote or parenthesis, a
dangling operator, `||`, a quote glued to a word) comes back unchanged, which is
today's behavior, and so does a nesting too deep to walk. It is idempotent.
"""

_OPERATORS = ("AND", "OR", "NOT")


class _Unreadable(Exception):
    """The text isn't a search string this module reads for sure."""


def _tokens(text):
    """[(kind, start, end)] for `text`: LPAREN, RPAREN, OP (AND/OR/NOT), TERM.

    A TERM is a quoted phrase (with any `~N` / `~"..."` proximity suffix) or a run of
    non-space characters up to a space, quote or parenthesis. A backslash escapes the
    next character. Raises _Unreadable for shapes the parser can't be sure of.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            out.append(("LPAREN" if ch == "(" else "RPAREN", i, i + 1))
            i += 1
            continue
        if ch == '"':
            j = _close_quote(text, i)
            # Proximity suffixes: `"a b"~3`, `"a"~3~"b"`, `"a"~3~"b"~"c"`.
            while j < n and text[j] == "~":
                j += 1
                while j < n and text[j].isdigit():
                    j += 1
                if j < n and text[j] == '"':
                    j = _close_quote(text, j)
            if j < n and not (text[j].isspace() or text[j] in "()"):
                raise _Unreadable("quote glued to a word")
            out.append(("TERM", i, j))
            i = j
            continue
        j = i
        while j < n:
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c.isspace() or c in '()':
                break
            if c == '"':
                raise _Unreadable("quote inside a word")
            j += 1
        j = min(j, n)
        word = text[i:j]
        if word in ("||", "&&"):
            raise _Unreadable("Lucene symbol operator")
        out.append(("OP" if word in _OPERATORS else "TERM", i, j))
        i = j
    return out


def _close_quote(text, i):
    """Index just past the quote that closes the phrase opened at text[i]."""
    j = i + 1
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == '"':
            return j + 1
        j += 1
    raise _Unreadable("unclosed quote")


def _parse_level(text, toks, pos, inserts):
    """Read one parenthesis level from toks[pos]; record the parentheses it needs in
    `inserts`. Returns (start, end, next_pos) of the level's items."""
    items = []  # (kind, start, end, op_word)
    while pos < len(toks):
        kind, s, e = toks[pos]
        if kind == "RPAREN":
            break
        if kind == "LPAREN":
            inner_start, inner_end, pos = _parse_level(text, toks, pos + 1, inserts)
            if pos >= len(toks) or toks[pos][0] != "RPAREN":
                raise _Unreadable("unclosed parenthesis")
            items.append(("TERM", s, toks[pos][2], None))
            pos += 1
            continue
        items.append((kind, s, e, text[s:e] if kind == "OP" else None))
        pos += 1
    _group_level(items, inserts)
    start = items[0][1] if items else None
    end = items[-1][2] if items else None
    return start, end, pos


def _group_level(items, inserts):
    """Wrap each OR-separated segment of one level that holds more than one item."""
    if not any(op == "OR" for _, _, _, op in items):
        _check_segment(items)
        return
    segments, current = [], []
    for item in items:
        if item[3] == "OR":
            segments.append(current)
            current = []
        else:
            current.append(item)
    segments.append(current)
    for seg in segments:
        _check_segment(seg)
    for seg in segments:
        if len(seg) > 1:
            inserts.append((seg[0][1], "("))
            inserts.append((seg[-1][2], ")"))


def _check_segment(seg):
    """A segment is `[NOT]* term ([AND] [NOT]* term)*`; anything else is unreadable."""
    if not seg:
        raise _Unreadable("operator with nothing beside it")
    expect_term = True
    for _, _, _, op in seg:
        if op is None:
            expect_term = False
        elif op == "NOT":
            expect_term = True
        elif op == "AND":
            if expect_term:
                raise _Unreadable("AND with nothing before it")
            expect_term = True
    if expect_term:
        raise _Unreadable("operator at the end")


def explicit_boolean_precedence(text):
    """`text` with parentheses around each AND-group that sits beside an OR, so
    Lucene's parser runs NOT > AND > OR. Unchanged when no level mixes OR with
    anything, or when the text can't be read for sure."""
    if not text or not isinstance(text, str) or "OR" not in text:
        return text
    try:
        toks = _tokens(text)
        if not any(kind == "OP" and text[s:e] == "OR" for kind, s, e in toks):
            return text
        inserts = []
        _, _, pos = _parse_level(text, toks, 0, inserts)
        if pos != len(toks):
            raise _Unreadable("unopened parenthesis")
    except (_Unreadable, RecursionError):  # RecursionError: parentheses ~1,000 deep
        return text
    if not inserts:
        return text
    # At one position a closing parenthesis goes before an opening one.
    inserts.sort(key=lambda x: (x[0], x[1] == "("))
    out, last = [], 0
    for at, ch in inserts:
        out.append(text[last:at])
        out.append(ch)
        last = at
    out.append(text[last:])
    return "".join(out)
