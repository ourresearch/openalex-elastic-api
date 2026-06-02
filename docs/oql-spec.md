# OQL (OpenAlex Query Language) Specification — v2 **(FROZEN)**

> **Status: frozen** (oxjob #330, 2026-06-02). This is a cases-first
> specification: the normative truth is the worked-example corpus
> [`docs/oql/corpus.yaml`](./oql/corpus.yaml), machine-checked by
> [`tests/oql/test_corpus_roundtrip.py`](../tests/oql/test_corpus_roundtrip.py).
> **The rules in this prose are the generalization *under* the cases.** When prose
> and a corpus case disagree, the case wins — fix the prose.
>
> v2 supersedes v1.1. v1.1 (parser/renderer in `query_translation/oql_*.py`) was
> designed months ago and never shipped; v2 is a "build one to throw away" rev
> (Brooks) — the general idea survives, many local decisions changed. The
> production translator is still v1.1; reconciling it to v2 is roadmap step 3 (see
> [`docs/oql/gap_report.md`](./oql/gap_report.md)).

OQL is the **human-readable surface over OQO**. It is defined and validated *in
terms of* OQO (the canonical query object, [`oqo-spec.md`](./oqo-spec.md)) — not
in terms of OXURL. Its whole bet, versus Scopus / Web of Science / Dimensions, is
that a researcher can **read a query aloud and roughly understand it** (confirmed
by the #277 peer survey: OQL is the only one of the four that does this).

---

## 0. Design principles (priority order)

1. **Human-readable / reads aloud.** Protect this above all.
2. **Map as tightly to OQO as possible.** OQO is canonical; OQL is sugar over it.
3. **When (1) and (2) conflict, decide case-by-case** — no global tiebreak.
4. **Cases > rules.** Rules emerge from worked examples; this doc leads with cases.
5. **Loud, never silent.** A query that can't do what it appears to do is an
   **error with a fix-it**, never a silent wrong answer.

## 1. The canonical triple and the round-trip invariant

```
URL  ↔  OQO  ↔  OQL          (OQO is canonical)
```

- **`OQL → OQO` is semantically lossless and order-preserving.** It discards only
  the **non-semantic text layer** — annotations/comments (display-name labels are a
  special case) and whitespace — and **normalizes equivalent spellings** to one
  canonical OQO (`is in` / `is any of` → one form; a technical column-id and its
  display name → one column).
- **`OQO → OQL` is deterministic** and *synthesizes* display-name labels.
- **Round-trip identity holds on the OQO side:** **`OQO → OQL → OQO` is the
  identity.** (`OQL-text → OQO → OQL-text` is *normalizing*, not identity —
  canonical spelling, regenerated `[names]`, comments gone.) This is how comments
  are allowed to exist without breaking "OQL is a pure function of OQO": they live
  only in the text layer, exactly like whitespace.

This invariant is the spec's runnable contract — see §9.

## 2. Statement shape

```
<entity> [ where <conditions> ] [ ; group by <dims> ] [ ; sort by <keys> ] [ ; sample <n> [ seed <s> ] ]
```

- The entity type names the rows returned (`works`, `authors`, `institutions`,
  `sources`, `publishers`, `funders`, `topics`, …). It is a sentence word →
  lowercase canonically; any case accepted on input. (corpus **A01**, **A07**, **A10–A12**)
- `where` introduces the conditions. With no conditions, the bare entity is a valid
  query: `works` (corpus **A01**).
- Directives (`group by`, `sort by`, `sample`) follow, each introduced by `;`.

OQL covers exactly **OQO Stage A (filter / sort / sample) + Stage B (group_by)**.
There is deliberately **no Stage-C / HAVING syntax** (§10).

## 3. Conditions — the cases

### 3.1 Entity references: the ID is authoritative, `[…]` is ignored decoration

```
works where institution is I136199984 [Harvard]                         (ENT1)
works where institution is I136199984 [those Harvard bastards, go Yale] (ENT2)
```
Both produce `{column_id: authorships.institutions.lineage, value: I136199984}`.

- **`[ … ]` is a universal annotation slot.** Its contents are **ignored on input**
  (never validated) and **regenerated as the entity's display name on output**. You
  may write anything inside it. It attaches to the token before it.
- The name **cannot lie**, because nothing reads it — this kills the v1.1
  silent-mismatch bug (where `Stanford [I136199984]` resolved to Harvard).
- The parser is **offline-pure**: no entity resolver in the parse path. A
  best-effort "⚠ that ID isn't Harvard" is the editor/linter's job, never the
  parser's, and never blocks.
- An entity reference with **only** an annotation and no ID is a **loud error**:
  `institution is [Harvard]` → `OQL_MISSING_ENTITY_ID` (corpus **ENT6**).
- Values are **bare** (no `entity/id` prefix): `I136199984`, `de`, `article`, `13`,
  `gold` — the column carries the namespace (per oqo-spec §2). A `col_…` collection
  reference is also a valid bare value (corpus **B04**).

### 3.2 Sets / value lists: `is any of ( … )`

```
works where institution is any of (I33213144 [Harvard], I97018004 [Stanford])  (ENT3)
works where type is in (article, review)                                       (ENT5)
works where institution is not any of (I33213144, I97018004)                   (ENT4)
```

- `( … )` does **double duty**: boolean grouping **and** value lists. The preceding
  keyword disambiguates.
- Accept **`is in`** and **`is any of`** on input; **emit `is any of`** canonically
  (it reads aloud; SQL familiarity is explicitly *not* a goal here).
- `is any of (a, b)` compiles to an OR-branch of equality leaves. `is not any of
  (a, b)` is `NOT(a OR b)` = `(NOT a) AND (NOT b)` by De Morgan — canonical NNF
  carries the negation on the leaves (corpus **ENT4**).

### 3.3 Delimiters and the no-escaping result

| Delimiter | Meaning |
|---|---|
| `( … )` | boolean grouping **and** value lists (`is any of ( … )`) |
| `[ … ]` | annotation slot — ignored on input, regenerated as a display name on output |
| `" … "` | literal text to match (a phrase) |
| `{ … }` | **unused** — banked for later |

**The language has no escape sequences at all.** Two lexing rules buy this:
1. **Strings are scanned opaquely** — any delimiter inside `" … "` (`[ ] ( ) ,`) is
   inert.
2. **An annotation runs to the first `]`** (no nesting, no `]` inside).

Therefore **only `"` delimits strings** — `'` is *not* a delimiter, so apostrophes
and contractions are ordinary characters: `"parkinson's disease"`, `child's`
(corpus **L21**). A literal `"` inside a search term is unsupported (ES normalizes
punctuation away, so it is meaningless anyway) and documented, not escaped.

### 3.4 Booleans, casing, precedence

```
works where title contains "foo" AND ("bar" OR "baz")    (BOOL1)  ✓
works where title contains "foo" AND "bar" OR "baz"       (BOOL2)  ✗ OQL_MIXED_BOOL_NEEDS_PARENS
works where title contains "a" AND "b" AND "c"           (BOOL3)  ✓ (pure-AND, associative)
works where title contains foo and (bar or baz)          (BOOL4)  ✓ (lowercase normalized to AND/OR)
```

- **Operators always sit OUTSIDE quotes.** Inside quotes, even `OR` is a literal
  word (§3.6 governing law).
- **`AND` / `OR` / `NOT` are UPPERCASE canonically**; lowercase accepted on input
  and normalized. Rule: **logical connectives uppercase; sentence words lowercase**
  (`where`, `is`, `contains`, `within`, `exactly`, `any of`).
- **Mixed AND/OR at one grouping level REQUIRES explicit parentheses — a loud error
  otherwise** (`OQL_MIXED_BOOL_NEEDS_PARENS`). Pure-AND or pure-OR runs are
  associative, so they need no parens. This is the **one deliberate departure** from
  WoS/Scopus muscle memory, and it is where the field is already heading (Scopus
  mid-migration; Dimensions enforces; Lucene/Sourcegraph advise full
  parenthesization). Canonical output fully parenthesizes mixed logic.
- **No implicit adjacency:** two operands with no connective between them is an
  error (`OQL_IMPLICIT_ADJACENCY`) — this is what lets us drop force-quoting and
  still disambiguate.

### 3.5 Negation — one mechanism

```
works where title & abstract contains covid AND title & abstract does not contain pediatric  (L15)
```
→ `{contains covid}` AND `{contains pediatric, is_negated: true}`.

There is **one** negation mechanism, mapping to OQO's `is_negated` (NNF). On the
surface it reads naturally — `is not`, `does not contain`, `is not any of`, or a
prefix `NOT (…)` on a group. All compile to `is_negated` on the appropriate node;
the canonical form pushes it to the leaves.

### 3.6 Search — the governing law

> **Outside the quotes = structure** (operators, list sugar, the modifiers
> `exactly` / `within N words`, the wildcards `*` `?`). **Inside the quotes =
> literal text**, matched as-is (modulo lemmatization). Operators inside quotes are
> just words; wildcards fire only when bare; two bare terms with no operator between
> them is an error.

OQO has exactly **one** text operator, `contains`. The search *mode* is split
across the **column** (lemmatization / semantic) and **inline value micro-syntax**
(phrase / proximity / wildcard); the **boolean** structure is the filter tree.

| Axis | OQL surface | OQO encoding |
|---|---|---|
| field scope | the field name (`title`, `title & abstract`, `abstract`, `anywhere`, `raw affiliation`, `byline`) | column prefix (`display_name.search`, `title_and_abstract.search`, `default.search`, …) |
| lemmatization | `exactly` keyword | column suffix `.search` (stemmed) vs `.search.exact` |
| semantic | `is similar to` | column suffix `.search.semantic` (2-phase) |
| adjacency (phrase) | `" … "` | quotes in the value |
| proximity | `within N words` | `"phrase"~N` in the value |
| wildcard | bare `*` / `?` | `*` / `?` in the value |
| boolean | infix `AND`/`OR`/`NOT`, `any of`/`all of` | the BranchFilter tree |

The 9 gauntlet cases pin the consequences (all are corpus rows):

| # | OQL (`title …`) | Result |
|---|---|---|
| G1 | `contains foo and (bar or baz)` | `foo AND (bar OR baz)`, lemmatized |
| G2 | `contains any of (foo, bar, baz)` | OR over the flat list |
| G3 | `contains any of (foo, "foo bar", exactly baz)` | per-item modifiers; leaves on different columns (`.search` ×2, `.search.exact` ×1) |
| G4 | `contains all of (foo, "foo or bar")` | AND; the `or` is **inside quotes = literal** |
| G5 | `contains foo and "bar OR baz"` | pure-AND; `OR` in quotes is a literal word (the sneaky one) |
| G6 | `contains exactly foo and bar` | `(exactly foo) AND bar` — `exactly` binds ONE operand |
| G7 | `contains foo and "bar"` | `"bar" ≡ bar` — quoting a single word is a **no-op** |
| G8 | `contains "bar*"` | ✗ `OQL_WILDCARD_IN_QUOTES` — fix-it: use `bar*` unquoted |
| G9 | `contains bar*` | bare prefix wildcard |

Key rules these encode:

- **Booleans are structural, never lexical.** `contains "foo or bar"` searches the
  literal phrase; the boolean is the tree (`contains any of ("foo", "bar")`).
- **Quotes mean PHRASE, not "disable stemming."** Stemming stays **ON** inside
  quotes → `contains "whopper junior"` matches "whoppers junior" (corpus **PW12**;
  the recall win, and the deliberate divergence from PubMed). To turn stemming off,
  use `exactly` (corpus **PW11**).
- **Quoting a single word is a no-op** (`"bar" ≡ bar`) — the corollary.
- **`exactly` binds a single operand** (term, phrase, group, or list). `exactly foo
  AND bar` = `(exactly foo) AND bar`; widen with parens: `exactly (foo AND bar)`.
  Canonical output parenthesizes a modifier's scope when a boolean is adjacent.
- **`is similar to "…"` is semantic** vector search (`.search.semantic`, corpus
  **PW10**).
- **`any of (…)` / `all of (…)`** are flat-list sugar for same-op OR / AND; mixed
  logic uses infix `AND`/`OR` + required parens. Both compile to the same tree.

### 3.7 Proximity and wildcards — the edge matrix

```
works where title contains "smart phone" within 3 words   (PW1)  ✓ → "smart phone"~3
works where title contains foo*bar                          (PW2)  ✓ mid-word *
works where title contains wom?n                            (PW3)  ✓ ? = exactly one char
works where title contains *cycle                           (PW4)  ✗ OQL_LEADING_WILDCARD
works where title contains ?cycle                           (PW5)  ✗ OQL_LEADING_WILDCARD
works where title contains ab*                              (PW6)  ✗ OQL_SHORT_WILDCARD_PREFIX (need ≥3)
works where title contains "smart phone*" within 3 words    (PW7)  ✗ OQL_WILDCARD_IN_QUOTES
works where title contains "smart" within 3 words of "phone"(PW8)  ✗ OQL_BINARY_PROXIMITY
works where title contains smart* within 3 words            (PW9)  ✗ OQL_WILDCARD_IN_PROXIMITY
```

- **Proximity is a whole-phrase modifier**, not a binary `X within N of Y`. ES slop
  is the total positional moves over one quoted phrase — it conflates gap *and*
  reordering (reversal alone costs 2). So `"smart phone" within 3 words` →
  `"smart phone"~3`, documented as "up to N positional moves apart, **in any
  order**." A binary form would lie about the semantics and not generalize to 3+
  terms → `OQL_BINARY_PROXIMITY`.
- On the multi-valued per-record search fields (`raw affiliation` /
  `byline`), a **quoted phrase scopes to one sub-record** (one affiliation / one
  byline) via ES `position_increment_gap`; slop widens within it. This is how a
  single `contains` leaf expresses intra-affiliation co-occurrence (corpus **L09**,
  **L19**, **L22**).
- **Wildcards fire only when BARE on a single token.** In quotes →
  `OQL_WILDCARD_IN_QUOTES`. Leading → `OQL_LEADING_WILDCARD`. Sub-3-char prefix →
  `OQL_SHORT_WILDCARD_PREFIX`. With proximity → `OQL_WILDCARD_IN_PROXIMITY`. Every
  unsupported combination is a loud error with a fix-it — never a silent literal,
  never a false promise. See [`docs/oql/engine_findings.md`](./oql/engine_findings.md)
  for the engine behavior behind these.

### 3.8 `null` / `unknown`

`language is unknown` / `language is not unknown` → `value: null` (± `is_negated`).
Emit `unknown` canonically; accept `null` and `unknown` on input.

### 3.9 Booleans on flags (`it's …`)

Boolean columns get a reads-aloud surface: `it's open access`, `it's not open
access`, `it's retracted`, `it has a DOI`, `it has an ORCID` (corpus **A05**,
**A08**, **B05**, **B08**). These compile to `{column: …, value: true|false}`. The
technical `<column> is true|false` form is also accepted.

## 4. Directives

```
authors; sort by works_count desc                          (A07)
works where year >= 1976; group by topic, year             (B03)  (multi-dim: spec-level; live API single-dim → #297)
works where … ; sort by citations desc; sample 500         (L07)
```

- **`group by <dim>[, <dim>]*`** → `group_by` list (order = dimension order).
- **`sort by <key> [asc|desc][, …]`** → ordered `sort_by` list (order = tiebreaker
  priority). Accept `ascending`/`descending`; default `asc`. Synthetic keys
  (`relevance_score`, `count`, `key`) are allowed.
- **`sample <n> [seed <s>]`** → `sample` (+ optional reproducibility `seed`).

## 5. Diagnostics (codes + fix-its)

Diagnostics are a **language-agnostic contract** (charter decision 5): every error
is a stable **code** + a human message + a **fix-it**; consumers (parser, editor,
NL) share codes and only localize prose. Every `✗` corpus row asserts its code.

| Code | When | Fix-it |
|---|---|---|
| `OQL_MIXED_BOOL_NEEDS_PARENS` | mixed AND/OR at one level | add parens: `a AND (b OR c)` |
| `OQL_IMPLICIT_ADJACENCY` | two operands, no connective | insert AND or OR |
| `OQL_MISSING_ENTITY_ID` | entity ref with only a `[name]` | put the ID first: `institution is I136199984 [Harvard]` |
| `OQL_WILDCARD_IN_QUOTES` | `*`/`?` inside a quoted phrase | move it out: `bar*` |
| `OQL_LEADING_WILDCARD` | leading `*`/`?` | anchor it: `cycle*` |
| `OQL_SHORT_WILDCARD_PREFIX` | `<3` chars before `*` | add characters: `abc*` |
| `OQL_WILDCARD_IN_PROXIMITY` | wildcard + `within N words` | drop one of them |
| `OQL_BINARY_PROXIMITY` | `X within N words of Y` | one phrase: `"x y" within N words` |
| `OQL_UNTERMINATED_STRING` / `OQL_UNTERMINATED_ANNOTATION` | missing `"` / `]` | close it |
| `OQL_UNKNOWN_FIELD` / `OQL_UNKNOWN_ENTITY` / `OQL_UNKNOWN_BOOLEAN` | not in the registry | check the properties registry |
| `OQL_MISSING_OPERATOR` / `OQL_MISSING_VALUE` / `OQL_BAD_NUMBER` | malformed clause | — |
| `OQL_UNBALANCED_PARENS` | missing `)` | add `)` |
| `OQL_BAD_SORT` / `OQL_BAD_SAMPLE` / `OQL_BAD_PROXIMITY` / `OQL_PROXIMITY_NEEDS_PHRASE` / `OQL_SEMANTIC_NEEDS_TEXT` / `OQL_TRAILING_TOKENS` | malformed directive/clause | — |

(The reference implementation `tests/oql/oql_v2.py` is the authoritative code list.)

## 6. Fields & values (the registry)

OQL field names, the columns they map to, value types, and valid operators are owned
by the **properties registry** (`/properties`; #294/#331), **not** by this spec.
The reference impl carries a focused stand-in (`tests/oql/oql_v2.py:_FIELDS`)
covering the corpus. Field validity ("is this column valid on this entity? what
value type? which operators?") is a registry question; OQL's grammar is
column-agnostic, exactly as the OQO dataclass is (oqo-spec §7).

## 7. The corpus (normative)

[`docs/oql/corpus.yaml`](./oql/corpus.yaml) is the normative set of `(OQL, OQO)`
pairs. It covers: every in-scope #284 worked-example row rendered to v2, the 9
gauntlet cases, the proximity/wildcard matrix, and the entity/boolean/set cases.
Each row is `ok` (round-trips), `error` (named diagnostic + fix-it), or `boundary`
(documented non-representable: `L02c` wildcard-in-proximity, `L12` acronym
resolution, `L20` set-reference).

**v2 corrections to #284 search rows** (noted per row in the corpus): exactness now
lives in the `.search.exact` column via `exactly` (L03), not in a quoted value;
multi-word phrases are explicitly quoted (A06, B02, …); loose multi-word search is
made explicit structure (L07, L17). These follow from §3.6's "quotes = phrase,
stemming ON."

## 8. Out of scope

- **Stage C / HAVING** (filtering on group aggregates). OQL must not promise what
  OQO can't execute (charter decision 2); the abandoned `get`/`summarize by`/`where
  …;` dialect (#274) is the trap to avoid. Group ranking by an aggregate metric
  (corpus **L18**) is `#297`.
- **Multi-dimensional `group by`** is expressible in the spec (corpus **B03**) but
  single-dimension in the live serving impl → `#297`.
- **Acronym / name resolution** (corpus **L12**) and **set-references** (corpus
  **L20**) are not query-language features.

## 9. Conformance & round-trip

The runnable contract:

```bash
cd ~/Documents/openalex-elastic-api
python3 -m venv .venv-oql && .venv-oql/bin/pip install -q pyyaml requests pytest
# round-trip identity (OQO -> OQL -> OQO) over the normative corpus:
.venv-oql/bin/python -m pytest tests/oql/test_corpus_roundtrip.py -q --noconftest
# gap report against the current v1.1 production translator:
.venv-oql/bin/python tests/oql/gap_report.py    # -> docs/oql/gap_report.md
```

The reference implementation (`tests/oql/oql_v2.py`) is the **executable spec** —
it is *not* the production translator (`query_translation/oql_*.py`, still v1.1).
Reconciling the two is roadmap step 3 (gated on #323); the gap report is its
work-list.

## 10. Related documentation

- [`oqo-spec.md`](./oqo-spec.md) — the canonical query object OQL is sugar over.
- [`oql/corpus.yaml`](./oql/corpus.yaml) — the normative cases.
- [`oql/gap_report.md`](./oql/gap_report.md) — v1.1 → v2 work-list.
- [`oql/engine_findings.md`](./oql/engine_findings.md) — engine reality behind the
  wildcard/proximity errors.
- `plans/oqlo.md` (oxjobs) — the OQLO charter (architecture, roadmap, decisions).
