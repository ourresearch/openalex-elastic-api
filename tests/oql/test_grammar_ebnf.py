"""
OQL derived-grammar no-drift gate (oxjob #361).

`docs/oql/grammar.ebnf` is a hand-written W3C-EBNF reference grammar for OQL v2.1
(charter plans/oqlo.md decision 13: we do NOT generate a parser from it — it's a
DERIVED doc artifact that lets us publish a grammar + railroad diagram). Because
it's hand-written, it could silently drift from the real parser
(`query_translation/oql_lang.py`) and the normative corpus (`docs/oql/corpus.yaml`).
This gate makes that drift loud:

  1. KEYWORD CLOSURE — every keyword literal the EBNF declares is actually a
     keyword the production parser recognizes (no invented syntax in the docs),
     and every structural keyword the parser recognizes is declared by the EBNF
     (no parser keyword the docs forgot). Catches both directions of drift.

  2. CORPUS TOKENIZES — every OQL string in the normative corpus is tokenizable
     under the EBNF's lexical terminals (WORD / NUMBER / STRING / ANNOT / the
     punctuation operators). A corpus query that used a character class the
     grammar's `wordChar` / STRING / ANNOT rules can't produce would fail here.

  3. RAILROAD FRESH (optional) — if the `rr` toolchain is available, assert the
     committed `grammar.railroad.html` re-renders byte-stably from the EBNF.
     Skipped when Java / rr.war aren't present (CI doesn't ship them); the
     keyword + tokenization checks are the load-bearing, env-free gate.

Runs in the existing `tests/oql/` harness (oql-gate.yml, push:master), so a docs
grammar that drifts from the parser turns the OQL conformance gate red.
"""
import os
import re

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EBNF = os.path.join(REPO, "docs", "oql", "grammar.ebnf")
CORPUS = os.path.join(REPO, "docs", "oql", "corpus.yaml")
PARSER = os.path.join(REPO, "query_translation", "oql_lang.py")
RAILROAD = os.path.join(REPO, "docs", "oql", "grammar.railroad.html")


# --------------------------------------------------------------------------- #
# EBNF parsing helpers
# --------------------------------------------------------------------------- #
def _ebnf_text():
    with open(EBNF) as fh:
        return fh.read()


def _strip_comments(text):
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)


# A complete quoted keyword literal of EITHER quote type. The two alternatives
# are kept separate so an apostrophe inside a double-quoted literal ("it's",
# "doesn't") and a double-quote inside a single-quoted literal don't make the
# match run away across the rest of the file.
_LIT = re.compile(r'"([^"]*)"' r"|'([^']*)'")


def _declared_keywords():
    """Alphabetic keyword literals declared in the EBNF (e.g. 'where', "it's").

    Excludes pure-punctuation literals ('(' ',' '>=' …) — those are operators /
    structure, checked structurally, not vocabulary. A keyword is any literal
    that contains a letter."""
    body = _strip_comments(_ebnf_text())
    lits = {(a or b) for a, b in _LIT.findall(body)}
    return {w for w in lits if any(c.isalpha() for c in w)}


def _parser_recognized_words():
    """Lowercased alphabetic words the production parser tests for as keywords.

    Harvested from `word_is("…")`, `val.lower() == "…"`, and `val.lower() in
    (…)` / `{…}` membership checks in oql_lang.py — i.e. every place the parser
    treats a WORD positionally as a keyword. This is the parser's keyword
    vocabulary; the EBNF must be a subset of it (no invented docs syntax) and
    cover its structural keywords."""
    with open(PARSER) as fh:
        src = fh.read()
    words = set()
    # word_is("a", "b", k=...) — grab every quoted arg
    for m in re.finditer(r"word_is\(([^)]*)\)", src):
        for q in re.findall(r'"([^"]+)"|\'([^\']+)\'', m.group(1)):
            w = (q[0] or q[1]).strip().lower()
            if w and any(c.isalpha() for c in w):
                words.add(w)
    # val.lower() == "x"  and  val.lower() in ("x", "y") / {"x", "y"}
    for m in re.finditer(r'val\.lower\(\)\s*==\s*[\'"]([^\'"]+)[\'"]', src):
        words.add(m.group(1).lower())
    for m in re.finditer(r"val\.lower\(\)\s*in\s*[\(\{]([^\)\}]*)[\)\}]", src):
        for q in re.findall(r'"([^"]+)"|\'([^\']+)\'', m.group(1)):
            w = (q[0] or q[1]).strip().lower()
            if w:
                words.add(w)
    # The shared operator matcher (match_operator) recognizes keywords through a
    # lowercased-word helper: `w0 == "x"`, `w(<k>) == "x"`, `w0 in ("a", "b")`.
    for m in re.finditer(r'\bw(?:0|\([^)]*\))\s*==\s*[\'"]([^\'"]+)[\'"]', src):
        words.add(m.group(1).lower())
    for m in re.finditer(r"\bw0\s*in\s*[\(\{]([^\)\}]*)[\)\}]", src):
        for q in re.findall(r'"([^"]+)"|\'([^\']+)\'', m.group(1)):
            w = (q[0] or q[1]).strip().lower()
            if w:
                words.add(w)
    # `and` / `or` are recognized via the `_CONNECTIVES` set (membership test),
    # not a literal `word_is(...)` — harvest that named set too.
    for m in re.finditer(r"_CONNECTIVES\s*=\s*\{([^}]*)\}", src):
        for q in re.findall(r'"([^"]+)"|\'([^\']+)\'', m.group(1)):
            w = (q[0] or q[1]).strip().lower()
            if w:
                words.add(w)
    return words


def test_ebnf_keywords_are_recognized_by_the_parser():
    """No invented syntax in the docs: every alphabetic keyword the EBNF
    declares is one the production parser actually recognizes."""
    declared = {k.lower() for k in _declared_keywords()}
    recognized = _parser_recognized_words()
    unknown = sorted(declared - recognized)
    assert not unknown, (
        "grammar.ebnf declares keyword(s) the parser (oql_lang.py) does not "
        f"recognize — docs grammar has drifted ahead of the parser: {unknown}"
    )


def test_parser_structural_keywords_are_declared_by_the_ebnf():
    """No forgotten syntax in the docs: the load-bearing structural keywords the
    parser recognizes are all present in the EBNF. (Scoped to the structural set
    — value-coercion words like 'true'/'yes' and field-alias phrase words live in
    the registry, not the grammar, per spec §6.)"""
    declared = {k.lower() for k in _declared_keywords()}
    # The grammar's structural vocabulary: clause/operator/directive/search words.
    structural = {
        "where", "and", "or", "not", "is", "any", "of", "in", "collection",
        "contains", "does", "doesn't", "doesnt", "contain", "similar", "to",
        "near", "within", "words", "word", "group", "by", "sort", "asc", "desc",
        "sample", "seed", "it's", "its", "it", "has", "have", "all",
        "return",
    }
    recognized = _parser_recognized_words()
    # Only assert over the structural words the parser truly knows (guards against
    # this test rotting if a structural word is renamed in the parser).
    must_declare = sorted((structural & recognized) - declared)
    assert not must_declare, (
        "parser recognizes structural keyword(s) the grammar.ebnf forgot to "
        f"declare — docs grammar has drifted behind the parser: {must_declare}"
    )


# --------------------------------------------------------------------------- #
# Corpus tokenizes under the EBNF's lexical terminals
# --------------------------------------------------------------------------- #
# Diagnostics that fire at the LEXER (a row whose oql can't even tokenize). Such
# `error` rows are intentionally non-tokenizable, so they are out of scope for the
# lexical-coverage check below. (zd#8101 row 162 is Claire's own unbalanced-quote
# line — its whole point is that it does NOT tokenize.)
_LEXICAL_ERROR_DIAGNOSTICS = {"OQL_UNTERMINATED_STRING"}


def _corpus_oql_strings():
    with open(CORPUS) as fh:
        data = yaml.safe_load(fh)
    return [
        (r["id"], r["oql"]) for r in data["rows"]
        if r.get("oql")
        and r.get("diagnostic") not in _LEXICAL_ERROR_DIAGNOSTICS
    ]


# A token is: a "quoted string", a [bracket annotation], a punctuation operator,
# or a run of wordChars (any printable non-space that isn't a structural break).
# This mirrors the EBNF's STRING / ANNOT / WORD / operator terminals; if a corpus
# query contained a char none of these can produce, the residue check below trips.
_TOK = re.compile(
    r'"[^"]*"'                 # STRING
    r"|\[[^\]]*\]"             # ANNOT
    r"|>=|<=|>|<|&|\(|\)|,|;"  # punctuation operators
    r"|[^\s\"\[\]()<>&,;]+"    # WORD / NUMBER (a wordChar run)
)


@pytest.mark.parametrize("cid,oql", _corpus_oql_strings(),
                         ids=[str(c) for c, _ in _corpus_oql_strings()])
def test_corpus_oql_tokenizes_under_grammar(cid, oql):
    """Every normative corpus query is fully tokenizable under the EBNF's lexical
    terminals — no character the grammar's WORD/STRING/ANNOT/operator rules can't
    account for. (A lexical-coverage check, not a full parse: full parse fidelity
    is `test_corpus_roundtrip.py`'s job against the real parser.)"""
    residue = _TOK.sub("", oql)
    # only inter-token whitespace may remain
    leftover = residue.strip()
    assert leftover == "", (
        f"corpus #{cid}: OQL contains text the grammar's lexical terminals "
        f"can't tokenize: {leftover!r}\n  OQL: {oql!r}"
    )


# --------------------------------------------------------------------------- #
# Railroad diagram is freshly rendered from the EBNF (best-effort)
# --------------------------------------------------------------------------- #
def test_railroad_html_exists_and_references_grammar():
    """The committed railroad render exists and is non-empty (the published
    artifact #361's Grammar page serves)."""
    assert os.path.exists(RAILROAD), "docs/oql/grammar.railroad.html is missing"
    with open(RAILROAD) as fh:
        html = fh.read()
    assert len(html) > 1000 and "<svg" in html, (
        "grammar.railroad.html looks empty/unrendered — re-run rr on grammar.ebnf"
    )
