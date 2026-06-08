# OQL (OpenAlex Query Language) Specification — v2 **(FROZEN)**

> **Status: frozen** (oxjob #330; v2.1, 2026-06-02 — adopted the mainstream
> search model after a peer review: **space = AND, quotes = exact, `near` =
> stemmed phrase**; lowercase connectives). This is a cases-first
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
  canonical OQO (an implicit-AND space-run and an explicit `and` → one form; a
  technical column-id and its display name → one column).
- **`OQO → OQL` is deterministic** and *synthesizes* display-name labels.
- **Round-trip identity holds on the OQO side:** **`OQO → OQL → OQO` is the
  identity.** (`OQL-text → OQO → OQL-text` is *normalizing*, not identity —
  canonical spelling, regenerated `[names]`, comments gone.) This is how comments
  are allowed to exist without breaking "OQL is a pure function of OQO": they live
  only in the text layer, exactly like whitespace.

This invariant is the spec's runnable contract — see §9.

## 2. Statement shape

```
<entity> [ where <conditions> ] [ group by <dims> ] [ sort by <keys> ] [ sample <n> [ seed <s> ] ]
```

- The entity type names the rows returned (`works`, `authors`, `institutions`,
  `sources`, `publishers`, `funders`, `topics`, …). It is a sentence word →
  lowercase canonically; any case accepted on input. (corpus rows **33**, **39**, **42–44**)
- `where` introduces the conditions. With no conditions, the bare entity is a valid
  query: `works` (corpus row **33**).
- Directives (`group by`, `sort by`, `sample`) follow, each introduced by its own
  keyword — no separating punctuation (oxjob #377). A leading `;` is still accepted
  on **input** for back-compat, but the canonical form never emits one.

OQL covers exactly **OQO Stage A (filter / sort / sample) + Stage B (group_by)**.
There is deliberately **no Stage-C / HAVING syntax** (§10).

### 2.1 Canonical formatting (output layout)

`OQO → OQL` lays the canonical string out **width-aware and multi-line** when it
is long, so a real systematic-review query (corpus row **78**, 114 search leaves)
reads as an indented tree instead of one ~1,600-char line. Because the parser is
**whitespace-blind** (whitespace is the non-semantic text layer, §1), the layout
is **OQO-identity-preserving by construction** — it cannot change meaning or break
any consumer. There is exactly **One Right Way** to lay a query out; it is a pure
function of the query, never of the input's whitespace.

Implemented in [`query_translation/oql_lang.py`](../query_translation/oql_lang.py)
(`format_oql`, reached via `render()` / `render_tree()`); the rules:

- **Target width 80 columns** (soft); **indent 2 spaces** per level.
- **Recursive fits-or-explode** (the Black model): render a node flat; if it
  fits at its starting column, keep it on one line; otherwise **explode its
  direct children one level and recurse**. Breaking a parent does **not** force
  its children to break.
- **Top level.** A statement that fits stays on one line. Otherwise the entity
  head, the `where` body, and **each directive** go on their own line(s); the
  directives (`group by …`, `sort by …`, `sample …`) sit at column 0.
- **Leading connectives.** When a boolean explodes, `and` / `or` **begin** each
  continuation line (one operand per line). A parenthesized group puts `(` on
  the current line, its operands one level deeper, and `)` back at the group's
  indent.
- **Value/term groups** (`is ( … )`, `contains ( … )`): inline if they fit; else
  **≤ 8 items → one per line**, **> 8 items → fill/pack** to the width (this is what
  tames row 78's synonym blocks).
- **The connective trails every item but the last** of an **exploded** group (the
  idempotence anchor + clean diffs); the parser is whitespace-blind, so the multi-line
  form re-parses to the identical OQO.
- **Idempotence is a hard invariant:** `format(format(x)) == format(x)`. Every
  break decision is a pure function of *(content, width, depth)*.
- **Hard ceiling 100 columns:** only a **single unbreakable atom** (one quoted
  phrase, ID, or term longer than the budget) may exceed the target; nothing
  with an internal ` or `/` and ` break point ever does.

```
works
where year >= 2020
  and title contains (
    fat or obese or obesity or overweight or thin or "anti fat" or "being fat" or
    "body esteem" or "body image" or "fat ideal" or "thin ideal" or "weight bias"
  )
sort by citation count desc
```

## 3. Conditions — the cases

### 3.1 Entity references: the ID is authoritative, `[…]` is ignored decoration

```
works where institution is I136199984 [Harvard]                         (row 1)
works where institution is I136199984 [those Harvard bastards, go Yale] (row 2)
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
  `institution is [Harvard]` → `OQL_MISSING_ENTITY_ID` (corpus row **6**).
- Values are **bare** (no `entity/id` prefix): `I136199984`, `de`, `article`, `13`,
  `gold` — the column carries the namespace (per oqo-spec §2). A `col_…` collection
  reference is also a valid bare value (corpus row **49**).

**Which values get a `[display name]` on output is per-column (registry-driven):**
the renderer synthesizes a name only when the bare value is **not human-readable** —
opaque OpenAlex IDs (`I136199984` → `[Harvard University]`) and **country codes**
(`de` → `[Germany]`). Already-readable slugs (`article`, `gold`, `en`) get **no**
annotation — `article [article]` is noise. This is a column property in the
properties registry (#294/#331), not an entity-vs-string distinction.

**Value case is cosmetic, not semantic.** The engine is case-insensitive on values
(verified live 2026-06-02: `US`==`us`, `Article`==`article`, `I136…`==`i136…`), so
OQL canonicalizes case purely for readability: **enum slugs → lowercase**
(`type is Article` → `type is article`), **ISO country codes → uppercase**
(`country is us` → `country is US`), and **IDs / search text → verbatim** (an
OpenAlex ID's uppercase prefix is conventional; search text is the user's literal
words). `col_…` references are always preserved. (Per-column canonical case is a
registry property.)

### 3.2 Sets / value groups: `is ( … )`  (parens-bag, #363)

```
works where institution is (I33213144 [Harvard] or I97018004 [Stanford])   (row 3)
works where type is (article or review)                                    (row 5)
works where institution is not (I33213144 or I97018004)                    (row 4)
works where country is (us and uk)                                         (row 92, D7)
```

- **The arity rule (one rule, both `is` and `contains`):** a list of **2+
  values/terms must be parenthesized**; a **single** value/term may be bare
  (`type is article`, `title contains cancer`). An *atom* is one bare word, one
  quoted phrase, or one parenthesized sub-group, so `"systematic review"` is a
  single atom and stays bare. `type is article review` → `OQL_UNDELIMITED_TERM_LIST`.
- This is the rule that **kills the silent keyword-truncation footgun**: a reserved
  word (`sort by`, `and`, …) can only "float" inside unquoted free text when there
  are 2+ unparenthesized terms — which the rule forbids.
- **Inside `( … )` is a boolean of atoms**: `or` / `and` / `not`, nesting allowed;
  the field + operator distribute over every atom. `country is (us or uk)` is an
  OR-branch of equality leaves; `country is (us and uk)` means works with **both** a
  US and a UK authorship (corpus row 92 — D7; for a single-valued field it is the
  empty set, which is coherent, not a footgun).
- `is not ( … )` negates the whole group: `is not (a or b)` = `NOT(a OR b)` =
  `(NOT a) AND (NOT b)` by De Morgan — canonical NNF carries the negation on the
  leaves and (since `filter_rows` is itself an implicit AND) renders as the explicit
  two-clause form `x is not a and x is not b` (corpus row **4**).
- **Removed:** the `any of` / `all of` / `is in` list keywords and comma-separated
  lists (`OQL_LIST_KEYWORD_REMOVED` / `OQL_COMMA_IN_GROUP`). `(a or b)` / `(a and b)`
  are strictly more expressive (they nest; flat keyword lists can't) and lose no
  capability. Re-adding `any of` later as a non-breaking accepted spelling is allowed.
- `( … )` does **double duty**: a clause-group at the clause level
  (`(year >= 2020 or it's open access)`) and a value/term group after an operator.
  The position disambiguates (a group right after `is`/`contains` is a value/term
  group; one where a clause is expected is a clause group).

### 3.2.1 Numeric ranges (#363)

A numeric field (`year`, `citation count`, `FWCI`) takes either a single number or a
**range** written with a hyphen, mirroring the OpenAlex URL range form:

```
works where year is 2019-2023        (>= 2019 AND <= 2023 — closed range)   (row 97)
works where FWCI is 1.5-3.0          (>= 1.5 AND <= 3.0 — floats allowed)    (row 99)
works where year >= 2019             (single-ended bound — stays an inequality)
```

- Only a **closed range** (both ends given) renders as the dash form. It is sugar for
  the two-bound implicit-AND `year >= 2019 and year <= 2023`; it parses to two bound
  leaves and (because `filter_rows` is an implicit AND) is indistinguishable from
  writing the two clauses.
- **A single-ended bound stays an inequality.** The open-range spellings `year is
  2019-` (>= 2019) and `year is -2023` (<= 2023) are **accepted on input** (a leading
  hyphen is always open-upper, never a negative — no numeric field takes negatives),
  but they **canonicalize back to the inequality form** `year >= 2019` / `year <=
  2023`. Only a two-ended range is written with a dash.
- **Strict bounds collapse on integer fields:** `year > 42 and year < 100` canonicalizes
  to the inclusive `year is 43-99` (a whole-number interval has an exact inclusive
  spelling). This applies only when a column carries **both** a lower and an upper
  bound; a lone `citation count > 100` keeps its strict inequality. Float fields (FWCI)
  have no clean ±1, so a strict float pair stays as two inequalities.

### 3.3 Delimiters and the no-escaping result

| Delimiter | Meaning |
|---|---|
| `( … )` | boolean grouping: a group of clauses **and** a group of values/terms (`is (a or b)`, `contains (a or b)`) |
| `[ … ]` | annotation slot — ignored on input, regenerated as a display name on output |
| `" … "` | literal text to match (a phrase) |
| `{ … }` | **unused** — banked for later |

**The language has no escape sequences at all.** Two lexing rules buy this:
1. **Strings are scanned opaquely** — any delimiter inside `" … "` (`[ ] ( ) ,`) is
   inert.
2. **An annotation runs to the first `]`** (no nesting, no `]` inside).

Therefore **only `"` delimits strings** — `'` is *not* a delimiter, so apostrophes
and contractions are ordinary characters: `"parkinson's disease"`, `child's`
(corpus row **78**). A literal `"` inside a search term is unsupported (ES normalizes
punctuation away, so it is meaningless anyway) and documented, not escaped.

### 3.4 Booleans, casing, precedence

```
works where title contains apple and title contains (banana or cherry)  (row 7)  ✓
works where title contains apple and banana or cherry      (row 8)   ✗ OQL_UNDELIMITED_TERM_LIST
works where title contains ("a" and "b" and "c")           (row 9)   ✓ (pure-AND, associative)
works where title contains FOO and (bar or baz)            (row 10)  ✓ (any case accepted on input)
```

- **Operators always sit OUTSIDE quotes.** Inside quotes, even `or` is a literal
  word (§3.6 governing law).
- **`and` / `or` / `not` are lowercase canonically**, but **case-insensitive on
  input** (`AND`, `And`, `and` all parse). Lowercase wins on output because
  principle #1 is "reads aloud," and the rule "**`and`/`or`/`not` outside quotes are
  *always* operators — quote them to search them literally**" removes any ambiguity
  with content words, so the uppercase-for-disambiguation convention scholarly DBs
  rely on buys us nothing. (All keywords are lowercase: `where`, `is`, `contains`,
  `within`, `near`, `and`/`or`/`not`.)
- **Mixed and/or at one grouping level REQUIRES explicit parentheses — a loud error
  otherwise** (`OQL_MIXED_BOOL_NEEDS_PARENS`). Pure-and or pure-or runs are
  associative, so they need no parens. This is the **one deliberate departure** from
  WoS/Scopus muscle memory, and it is where the field is already heading (Scopus
  mid-migration; Dimensions enforces; Lucene/Sourcegraph advise full
  parenthesization). Canonical output fully parenthesizes mixed logic.
- **Adjacency (space) = AND between *search terms* inside a `( … )` group** (§3.6):
  `title contains (climate change)` = climate AND change. At the top level a 2+ term
  list must be parenthesized (`title contains climate change` → `OQL_UNDELIMITED_TERM_LIST`,
  §3.6 row 17), and inside a group a space mixed with an explicit `or` still needs
  nested parens (`(climate change or warming)` → `OQL_MIXED_BOOL_NEEDS_PARENS`).
  Between *whole clauses* at the top level a connective is still required
  (`year >= 2020 and it's open access`); two full clauses jammed together with no
  `and` is `OQL_IMPLICIT_ADJACENCY`.

### 3.5 Negation — one mechanism

```
works where title/abstract contains covid and title/abstract does not contain pediatric  (row 71)
```
→ `{contains covid}` AND `{contains pediatric, is_negated: true}`.

There is **one** negation mechanism, mapping to OQO's `is_negated` (NNF). On the
surface it reads naturally — `is not`, `does not contain`, `is not (…)`, or a
prefix `not (…)` on a group. All compile to `is_negated` on the appropriate node;
the canonical form pushes it to the leaves.

**`not` binds to the single operand that follows it** (one term, leaf, or
parenthesized group) — `not a and b` is `(not a) and b`, **not** `not (a and b)`.
This is the *one* binding rule in OQL, and unlike AND/OR ordering (§3.4) it is kept
rather than parens-forced, for a reason: "unary NOT is tightest" is **universal and
unambiguous** (Lucene, PubMed, WoS, every programming language agree), whereas
AND-vs-OR ordering is *not* standardized across systems — so the footgun the
parens-rule guards against doesn't exist here. To negate a group, parenthesize:
`not (a or b)`. Canonical output always renders the scope explicitly (e.g.
`does not contain a and contains b`), so the binding is never hidden on round-trip.

### 3.6 Search — the governing law

> **Stemming is ON by default; quotes are the only thing that turns it off.**
> A **space** between words is **AND** (the Google/PubMed convention — verified to
> match OpenAlex's own engine). **Quotes = an exact, adjacent phrase** (no
> stemming) — single word or many. **`near "…"`** is the bridge: an adjacent
> phrase that *stays* stemmed (recall). Outside quotes = structure; inside quotes =
> literal text (even `or` is just a word there).

This is the mainstream model (Google, Bing, PubMed, Web of Science, Elasticsearch
all do space=AND and quotes=exact), chosen after surveying peers — see the design
note in `plans/oqlo.md` and oxjob #330's research. OQO has exactly **one** text
operator, `contains`; the *mode* is split across the **column** (stemmed vs exact
vs semantic) and **inline value micro-syntax** (phrase / proximity / wildcard); the
**boolean** structure is the filter tree.

| Axis | OQL surface | OQO encoding |
|---|---|---|
| field scope | the field name (`title`, `title/abstract`, `abstract`, `full text`, `raw affiliation`, `byline`) | column prefix (`display_name.search`, `title_and_abstract.search`, `fulltext.search`, …) |
| stemming | **default ON**; quotes turn it OFF | column suffix `.search` (stemmed) vs `.search.exact` |
| stemmed phrase | `near "…"` | `.search` with a quoted value |
| semantic | `is similar to "…"` | column suffix `.search.semantic` (2-phase) |
| adjacency (phrase) | `" … "` | quotes in the value |
| proximity | `within N words` | `"phrase"~N` in the value |
| wildcard | bare `*` / `?` | `*` / `?` in the value |
| boolean | space (=AND) / infix `and`/`or`/`not` inside `( … )` | the BranchFilter tree |

The gauntlet pins the consequences (all are corpus rows):

| row | OQL (`title contains …`) | Result |
|---|---|---|
| 11 | `(climate change)` | **space inside a group = stemmed AND**; words may be apart (recall). The default. |
| 12 | `"climate change"` | **quotes = exact adjacent phrase**, no stemming (`.search.exact`) |
| 13 | `near "whopper junior"` | **`near` = stemmed adjacent phrase** → matches "whoppers junior" |
| 14 | `"cat"` | quoting a **single** word = exact (no plurals) — quotes always mean exact |
| 15 | `cat` | bare word = stemmed (matches cats) — a single bare term is fine |
| 16 | `"rock or roll"` | inside quotes = literal: `or` is a word, one exact phrase |
| 17 | `climate change or warming` | ✗ `OQL_UNDELIMITED_TERM_LIST` — 2+ bare terms must be parenthesized |
| 18 | `(climate and (change or warming))` | ✓ `climate AND (change OR warming)` — the disambiguated form |
| 19 | `"bar*"` | ✓ quoted wildcard = the sanctioned path → no-stem `.search.exact` (oxjob #364) |
| 20 | `bar*` | ✗ `OQL_WILDCARD_NEEDS_EXACT` — bare wildcard is stemmed (wrong); fix-it: quote it `"bar*"` |

Key rules these encode:

- **A single bare term is fine; 2+ bare terms must be parenthesized** (the arity
  rule, §3.2). `title contains cancer` ✓; `title contains climate change` →
  `OQL_UNDELIMITED_TERM_LIST` (row 17) — this is the rule that kills the silent
  keyword-truncation footgun. **Inside a `( … )` group**, a space = AND, and there is
  **no silent order of operations**: mixing a space-run with an explicit `or` at one
  level is `OQL_MIXED_BOOL_NEEDS_PARENS`. `(climate change or warming)` errors; you
  say which you mean — `(climate (change or warming))` (row 18) or
  `((climate change) or warming)`. (Pure runs — all-space, all-`and`, all-`or` —
  need no inner parens.)
- **Quotes = exact, single word or phrase.** `"cat"` excludes "cats"; `"climate
  change"` is the adjacent, unstemmed phrase. This is the mainstream "quotes = exact
  match" people already expect.
- **`near "…"` = the stemmed phrase** — adjacent *and* lemmatized (`.search`), for
  when you want phrase precision without losing recall (corpus rows **13**, **32**).
  Without quotes you don't need `near`: bare terms are already stemmed.
- **Booleans are structural, never lexical.** `contains "foo or bar"` searches the
  literal phrase; the boolean is the tree (`contains (foo or bar)`).
- **`is similar to "…"` is semantic** vector search (`.search.semantic`, corpus
  row **30**).
- **A parenthesized group holds a boolean of terms** (`contains (a or (b and c))`);
  items may themselves be `"exact"` or `near "stemmed"` phrases. The `any of`/`all of`
  list keywords were removed (§3.2).
- **A search value runs until the next field-clause.** `title contains (a or b) and
  year >= 2020` is `(title contains (a or b)) and year >= 2020` — the `or` is the
  contains-group's, the `and` joins clauses. This is deterministic, not a precedence
  choice: a `year >= …` clause can't live *inside* a `contains`, so the value
  boundary is forced. A genuinely mixed and/or *between clauses* still errors (§3.4).

### 3.7 Proximity and wildcards — the edge matrix

```
works where title contains "smart phone" within 3 words      (row 21) ✓ exact proximity → .search.exact "smart phone"~3
works where title contains near "smart phone" within 3 words (row 32) ✓ stemmed proximity → .search "smart phone"~3
works where title contains "foo*bar"                        (row 22) ✓ mid-word * (quoted = no-stem .search.exact)
works where title contains "wom?n"                          (row 23) ✓ ? = exactly one char (quoted = no-stem)
works where title contains bar*                             (row 20) ✗ OQL_WILDCARD_NEEDS_EXACT (bare = stemmed = wrong)
works where title contains *cycle                           (row 24) ✗ OQL_LEADING_WILDCARD
works where title contains ?cycle                           (row 25) ✗ OQL_LEADING_WILDCARD
works where title contains ab*                              (row 26) ✗ OQL_SHORT_WILDCARD_PREFIX (need ≥3)
works where title contains "smart phone*" within 3 words    (row 27) ✓ wildcard-in-proximity → ES intervals (oxjob #355)
works where title contains "smart" within 3 words of "phone"(row 28) ✗ OQL_BINARY_PROXIMITY
works where title contains smart* within 3 words            (row 29) ✗ OQL_WILDCARD_IN_PROXIMITY
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
  single `contains` leaf expresses intra-affiliation co-occurrence (corpus rows **65**,
  **75**, **77**).
- **Wildcards require the no-stem (exact) field — quote them (oxjob #364).** A
  wildcard matches indexed tokens literally, but the default search is *stemmed*
  at index time, so a bare wildcard hunts for a prefix the index no longer holds
  and returns near-nothing (`studies*` = 2.4k stemmed vs 2.2M no-stem). So a wildcard
  on a single token must be **quoted** → it runs on `.search.exact`: `"bar*"`,
  `"foo*bar"`, `"wom?n"`. A **bare** wildcard is `OQL_WILDCARD_NEEDS_EXACT` (fix-it:
  quote it). `near` keeps a phrase stemmed, so a wildcard there is the same error.
  Leading → `OQL_LEADING_WILDCARD`. Sub-3-char prefix → `OQL_SHORT_WILDCARD_PREFIX`.
  Bare wildcard with proximity → `OQL_WILDCARD_IN_PROXIMITY`. Every unsupported
  combination is a loud error with a fix-it — never a silent literal, never a false
  promise. (This **reverses** #337's old `OQL_WILDCARD_IN_QUOTES` "move it out of the
  quotes" guidance: quotes are now exactly where wildcards belong.) See
  [`docs/oql/engine_findings.md`](./oql/engine_findings.md) for the engine behavior.

> **⚠ Acknowledged limitation (to be fixed, not a permanent boundary):**
> **wildcard-in-a-phrase / wildcard-near-another-word** — `"unusual behavi*or"`,
> `"smart phone*" within 3 words` — is rejected today (rows 27, 29, corpus row 58)
> because our ES `query_string` path drops the wildcard (verified live: row 58
> silently dropped it). **WoS and Scopus support this**, so it is a real
> capability gap, not a design choice. ES *can* express it with heavier query
> types (intervals / span queries); reaching it is future engine work — exactly
> what the "lift proximity/wildcard into OQO **structure**" recommendation enables
> (charter §4; adjacent to #298 / #337). Note: a wildcard **on its own word** —
> `behavi*or` (UK/US spelling) — works fine today; only the *combination with a
> phrase/proximity* is gapped, and you can often sidestep it with `contains x and
> y*` when the words needn't be adjacent.

### 3.8 `null` / `unknown`

`language is unknown` / `language is not unknown` → `value: null` (± `is_negated`).
Emit `unknown` canonically; accept `null` and `unknown` on input.

### 3.9 Booleans on flags (`it's …`)

Boolean columns get a reads-aloud surface: `it's open access`, `it's not open
access`, `it's retracted`, `it has a DOI`, `it has an ORCID` (corpus rows **37**,
**40**, **50**, **53**). These compile to `{column: …, value: true|false}`. The
technical `<column> is true|false` form is also accepted.

### 3.10 Collection membership: `is in collection`

```
works where work is in collection col_abc123                       (same-type: works in a Collection of works)
works where author is in collection col_xyz789                     (cross-type: works by authors in a Collection of authors)
works where country is in collection col_eu27                      (row 5x — predefined country set)
works where work is not in collection col_abc123                   (negation via the is_negated bit)
```

A **Collection** is a named, predefined or user-saved set of entities, addressed by a
`col_<base58>` id (`^col_[A-Za-z0-9]{1,48}$`). Membership is its own operator — distinct
from `is` / `is (…)` — because the intent ("is a member of this named set") and its
value space (a Collection picker) differ from value equality; this keeps the operator→value
model clean for the editor and downstream tooling.

- **Surface:** `<subject> is [not] in collection <col_id>`. `not` negates via the single
  `is_negated` mechanism (§3.5), never a separate operator.
- **OQO:** `operator: "in collection"`, `value: <col_id>`, on a leaf. One collection per
  clause (v1); union several via `or` clauses.
- **Same-type** (the Collection is of the queried entity, e.g. works on `/works`): the subject
  is the entity itself and the OQO uses `column_id: collection`, mirroring the dedicated
  `filter=collection:<col_id>` API param.
- **Cross-type** (the Collection is of a *referenced* entity, e.g. a set of authors/countries):
  the OQO keeps the referenced entity's `column_id` (e.g. `authorships.countries`) and renders
  to the bare `filter=<field>:<col_id>` URL surface. `col_…` ids are always preserved verbatim
  (never case-folded), as elsewhere.
- **URL round-trip:** a working prod URL carrying a `col_…` value (`collection:col_…` or
  `<field>:col_…`) parses back to the canonical `is in collection` form, so the triple holds.

## 4. Directives

```
authors sort by works_count desc                           (row 39)
works where year >= 1976 group by topic, year              (row 48)  (multi-dim: spec-level; live API single-dim → #297)
works where … sort by citation count desc sample 500            (row 63)
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
| `OQL_MIXED_BOOL_NEEDS_PARENS` | mixed and/or at one level | add parens: `a and (b or c)` |
| `OQL_IMPLICIT_ADJACENCY` | two operands, no connective | insert an `and` or `or` |
| `OQL_MISSING_ENTITY_ID` | entity ref with only a `[name]` | put the ID first: `institution is I136199984 [Harvard]` |
| `OQL_WILDCARD_NEEDS_EXACT` | bare (stemmed) `*`/`?` wildcard | quote it: `"bar*"` (runs on no-stem `.search.exact`) |
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

### 6.1 Value-domain validation (strict membership)

OQL is **readable in form but strict in validation**: a column whose value is drawn
from a *closed* vocabulary must carry a literal member of that vocabulary. Validation
is not lenient on these — name-based or fuzzy matching is the **NL parser's** job
(#344), never raw OQL. So `country is Canada` (the value is the name, not the code)
and `country is 42` are **errors** (`invalid_value`), not silently-matches-nothing
queries. They are NOT auto-resolved to `ca`; the validator offers a "did you mean
'ca'?" fix-it but the query is still rejected. (oxjob #363.)

The closed vocabularies (keyed by the property's `entity_type`, validated against the
same `config/<vocab>.yaml` tables the renderer resolves display names from — a value
validates **iff** it can also be rendered with a name):

| `entity_type` | canonical value form | example valid / invalid |
|---|---|---|
| `countries`   | ISO 2-letter, uppercased | `us`, `gb` / `uk`, `Canada`, `42` |
| `languages`   | ISO 2-letter code        | `en` / `english` |
| `sdgs`        | numeric id `1`–`17`      | `3` / `99` |
| `work-types`  | type slug                | `article`, `review` / `boguskind` |
| `oa-statuses` | status slug              | `gold`, `green` / `sparkly` |
| `continents`  | Wikidata Q-id            | `q15` |

> `gb` is the ISO code for the United Kingdom; `uk` is **not** a valid code and is
> rejected (the NL phrasings "UK"/"Britain"/"United Kingdom" all resolve to `gb`).

Membership descends into value groups, so each leaf of `country is (us or canada)`
is checked independently. **Open** ID entities (authors / works / institutions /
sources / … — millions of members) are not membership-checked here; they get an
ID-shape check instead (prefix + form, e.g. `I\d+`). Free-text `*.search` / `phrase`
values and raw strings are never membership-checked.

## 7. The corpus (normative)

[`docs/oql/corpus.yaml`](./oql/corpus.yaml) is the normative set of `(OQL, OQO)`
pairs. It covers: every in-scope #284 worked-example row rendered to v2, the 9
gauntlet cases, the proximity/wildcard matrix, and the entity/boolean/set cases.
Each row is `ok` (round-trips), `error` (named diagnostic + fix-it), or `boundary`
(documented non-representable: row `58` wildcard-in-proximity, row `68` acronym
resolution, row `76` set-reference).

**v2 search encoding vs. #284** (noted per row in the corpus): under §3.6's
mainstream model, a bare multi-word search is **stemmed AND** — exactly what the
#284 OXURLs did (space = AND on `.search`), so `climate change` (row 38), `quantum
computing` (row 72) etc. render as bare terms. A genuine adjacent phrase uses `near
"…"` (stemmed: rows 47, 51, 55, 56, 63, 65, 75, 77) or plain quotes when the
intent is exact/no-lemmatization (`"oyster toadfish"`, row 59).

## 8. Out of scope

- **Stage C / HAVING** (filtering on group aggregates). OQL must not promise what
  OQO can't execute (charter decision 2); the abandoned `get`/`summarize by`/`where
  …;` dialect (#274) is the trap to avoid. Group ranking by an aggregate metric
  (corpus row **74**) is `#297`.
- **Multi-dimensional `group by`** is expressible in the spec (corpus row **48**) but
  single-dimension in the live serving impl → `#297`.
- **Acronym / name resolution** (corpus row **68**) and **set-references** (corpus
  row **76**) are not query-language features.

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
