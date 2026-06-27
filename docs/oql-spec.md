# OQL (OpenAlex Query Language) Specification — v2 **(FROZEN)**

> **Status: frozen** (oxjob #330; v2.1, 2026-06-02 — adopted the mainstream
> search model after a peer review: **space = AND, quotes = exact, `stemmed` =
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
- **Operand order is the user's (decision 30, #363).** The order of clauses (the
  implicit top-level AND of `filter_rows`) and of values inside `is ( … )` /
  `has ( … )` groups is **preserved**, not alphabetized — for OQL-text and
  builder/direct-OQO input alike. So the LEGO builder never jumps a freshly-added
  clause to an alphabetical slot, and a systematic-review author's block order is
  kept. **Consequence:** OQO is no longer a *single* canonical form on the OQL
  side — `where A and B` and `where B and A` are distinct OQO (idempotence still
  holds: `OQO → OQL → OQO` is a fixed point). **Exception — the legacy ox-URL and
  NL→OQO paths sort operands alphabetically** into one canonical order: their input
  order is machine-shaped, not author-meaningful, and a deterministic order keeps
  their translation CI stable (this is also where decision 24's lower-bound-then-
  upper-bound numeric ordering applies).

This invariant is the spec's runnable contract — see §9.

## 2. Statement shape

```
<entity> [ where <conditions> ] [ group by <dims> ] [ sample <n> [ seed <s> ] ]
```

- The entity type names the rows returned (`works`, `authors`, `institutions`,
  `sources`, `publishers`, `funders`, `topics`, …). It is a sentence word →
  lowercase canonically; any case accepted on input. (corpus rows **33**, **42–44**)
- `where` introduces the conditions. With no conditions, the bare entity is a valid
  query: `works` (corpus row **33**).
- Directives (`group by`, `sample`) follow, each introduced by
  its own keyword — no separating punctuation (oxjob #377). A leading `;` is still
  accepted on **input** for back-compat, but the canonical form never emits one.

OQL covers exactly **OQO Stage A filtering + Stage B (group_by)**. Result-display
concerns — **sort order** (`OQO.sort_by`) and **column projection**
(`OQO.select`) — are deliberately **not** part of the OQL surface (oxjob #504);
they are driven by the URL (`?sort=` / `?select=`) and the GUI's own controls. There
is deliberately **no Stage-C / HAVING syntax** (§10).

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
  directives (`group by …`, `sample …`) sit at column 0.
- **Leading connectives — everywhere (oxjob #363, decision 25).** When *anything*
  explodes, `and` / `or` **begin** each continuation line (the first operand is
  bare; every later one is prefixed by the connective). This holds at the boolean
  `where` body **and** inside value/term groups — they read the same. A
  parenthesized group puts `(` on the current line, its operands one level
  deeper, and `)` back at the group's indent.
- **Value/term groups** (`is ( … )`, `has ( … )`): inline if they fit; else
  **> 8 items that all fit the width → fill/pack** (this is what tames row 78's
  synonym blocks) — a *wrapped* line begins with the connective; otherwise **one
  item per line**, and an item that is itself an over-width parenthesized
  sub-group **explodes recursively** (a §3.2.2-merged clause nests whole OR-blocks
  inside an AND; each block gets the same treatment, its open paren carrying the
  leading connective).
- **Why leading, not trailing.** `and`/`or` are **infix** — they can never sit on
  the last line the way a trailing comma can — so the Python/Black trailing-comma
  "clean append" trick doesn't transfer. With leading connectives, appending an
  item dirties **one** line (the new one); a trailing form would dirty **two** (the
  old last item gains a connective + the new line). The parser is whitespace-blind,
  so either form re-parses to the identical OQO; leading just gives the cleaner
  diff and a single rule across the whole tree.
- **Idempotence is a hard invariant:** `format(format(x)) == format(x)`. Every
  break decision is a pure function of *(content, width, depth)*.
- **Hard ceiling 100 columns:** only a **single unbreakable atom** (one quoted
  phrase, ID, or term longer than the budget) may exceed the target; nothing
  with an internal ` or `/` and ` break point ever does.

```
works where year >= 2020
  and title has (
    fat or obese or obesity or overweight or thin or "anti fat" or "being fat"
    or "body esteem" or "body image" or "fat ideal" or "thin ideal"
    or "weight bias"
  )
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

- **The arity rule (one rule, both `is` and `has`):** a list of **2+
  values/terms must be parenthesized**; a **single** value/term may be bare
  (`type is article`, `title has cancer`). An *atom* is one bare word, one
  quoted phrase, or one parenthesized sub-group, so `"systematic review"` is a
  single atom and stays bare. `type is article review` → `OQL_UNDELIMITED_TERM_LIST`.
- This is the rule that **kills the silent keyword-truncation footgun**: a reserved
  word (`group by`, `and`, …) can only "float" inside unquoted free text when there
  are 2+ unparenthesized terms — which the rule forbids.
- **Inside `( … )` is a boolean of atoms**: `or` / `and` / `not`, nesting
  allowed; the field + operator distribute over every atom. `country is (us or uk)`
  is an OR-branch of equality leaves; `country is (us and uk)` means works with
  **both** a US and a UK authorship (corpus row 92 — D7; for a single-valued field
  it is the empty set, which is coherent, not a footgun). Negation inside a group is
  the bare prefix `not` binding the next atom (`has (cancer and not mouse)`,
  §3.5).
- **Search values are the exception (D2 reversal, #363):** for a `has ( … )`
  search group, a **maximal run of bare connective-free words is ONE value node**
  (stemmed, adjacency-boosted), not a distributed AND of per-word leaves —
  `title/abstract has (mental health)` is a single
  `{title_and_abstract.search: "mental health"}` leaf. The engine adjacency-boosts
  the whole run (`match_phrase`), so splitting it would silently change ranking;
  recall is unaffected (cross-field AND, #399). Explicit `and`/`or`/`not` still build
  the tree *between* such nodes (`(mental health or anxiety)` = two nodes OR'd). See
  §3.6 and corpus rows 126–127. *(This reverses the earlier "space inside a group =
  AND" rule for **search** values; it still holds for **enum/value** groups like
  `country is (us and uk)` above.)*
- `not (a or b)` negates the whole group: `NOT(a OR b)` = `(NOT a) AND (NOT b)` by
  De Morgan — canonical NNF carries the negation on the leaves, and the canonical
  render keeps the group together with the `not`s inside: `x is (not a and not b)`
  (corpus row **4**; see §3.2.2 and §3.5). (`is not (a or b)` is an accepted input
  spelling for the same thing.)
  - **One separator per level** — `or`/`and` inside a `( … )` group, not commas;
    a comma in a group is `OQL_COMMA_IN_GROUP`.
- **Removed:** the `any (…)` / `all (…)` / `any of` / `is in` list keywords and
  comma-separated lists. `(a or b)` / `(a and b)` are strictly more expressive
  (they nest; flat keyword lists can't) and lose no capability.
- `( … )` does **double duty**: a clause-group at the clause level
  (`(year >= 2020 or open access is true)`) and a value/term group after an operator.
  The position disambiguates (a group right after `is`/`has` is a value/term
  group; one where a clause is expected is a clause group).

### 3.2.1 Numeric bounds and ranges (#363, decision 24)

A numeric field (`year`, `citation count`, `FWCI`) takes a single number, or a range
written as **explicit endpoint clauses** with the comparison operators:

```
works where year >= 2019 and year <= 2023        (closed range — two endpoint clauses)   (row 97)
works where FWCI >= 1.5 and FWCI <= 3.0          (floats allowed)                          (row 99)
works where year >= 2019                          (single-ended bound)
works where year > 42 and year < 100              (strict bounds — stay strict)             (row 100)
```

- **There is no dash range literal.** The `year is 2019-2023` / open-ended `year is
  2019-` / `year is -2023` spellings were **removed** as OQL surface syntax (decision
  24): write the explicit endpoints instead. This makes the parser simpler (a numeric
  value is a pure number, not a "mostly-int string"), buys clean type-checking, and
  fits OQL's picky/precise philosophy. Typing a dash range on a num field is a **hard
  error** (`OQL_RANGE_LITERAL_REMOVED`, row 179) with a fix-it echoing the endpoint
  form — *not* a lenient parse, and *not* a generic "not a number".
- **A closed range is the two-bound implicit-AND** `year >= 2019 and year <= 2023`.
  Because `filter_rows` is an implicit AND, the two clauses round-trip as two bound
  leaves; the canonical render is lower-bound-then-upper-bound.
- **Strict bounds stay strict — no inference.** `year > 42 and year < 100` renders
  exactly as written; it is **not** rewritten to the inclusive `year >= 43 and year <=
  99`. (The old ±1 strict-integer-pair collapse, which fed the removed dash literal,
  was dropped with it.)
- **The OpenAlex URL range form is unaffected.** `publication_year:2019-2023` (and
  `fwci:1.5-3.0`, the open `:-2023`, strict `:>42`) still parse from URLs and still
  render *to* URLs from the bound leaves — only the OQL *surface literal* went away, so
  URL round-trip survives.

### 3.2.2 Canonical render merges same-field structure (decision 20, #432/#363)

Published systematic reviews are **search-term trees** — "this term and that term,
but not that term" — written to be plugged whole into one text search; they are not
filter-triple trees. Canonical OQL therefore renders all the boolean structure that
belongs to **one field** as **one clause**, the tree inside the value group:

```
works where title has ((vape or vaping) and (health or harm))
works where title has (not dog and cat)
works where country is (not FR and US)
works where institution is (not I33213144 [Harvard] and not I97018004 [Stanford])   (row 4)
```

- **The rule:** among the children of one boolean node — including the implicit
  top-level AND of the filter rows — the items sharing one **(field,
  base-operator)** pair merge into a single `field op ( tree )` clause, the boolean
  structure preserved inside the parens. A negated leaf renders as a bare `not
  <atom>` prefix (§3.5), merged or standalone alike (`title has not dog`,
  `country is not FR`, `title has (not dog and cat)`).
- **All filter kinds**, not just search: `country is (not FR and US)` is canonical
  exactly like its `has` twin. Search groups merge by **base field** (a
  stemmed `.search` leaf and an exact `.search.exact` leaf share one group — that
  mix is the row-78 expressiveness win); `is` groups merge by column.
- **The principled boundary:** comparison operators live on the leaf (`>=`, `<`),
  so mixed-comparator pairs never merge — bound endpoints stay as separate clauses
  (`year >= 2019 and year <= 2023`, §3.2.1, decision 24). Null (`is unknown`),
  collection membership, semantic search, and bool/date columns keep their own
  surfaces and never merge. Cross-field structure necessarily stays multi-clause.
- **OQO is untouched.** Canonical OQO remains maximally distributed (NNF,
  leaf-level `is_negated`, top-level AND = `filter_rows`); the parser still
  distributes the field over every atom (§3.2). This rule is **render-direction
  only** — it makes OQO→OQL emit the same forms OQL→OQO already accepts, so the
  round-trip identity (§1) is preserved by construction.
- **Ordering inside the merged group** follows the same operand-order rule as
  everything else (§1, decision 30): the user's given value order is preserved on
  the OQL/builder path, and alphabetized only on the legacy-URL / NL paths. Merged
  and hand-written groups therefore read the same.
- Decided in **#432** (the SR branch/leaf "One Right Way"), charter decision 20,
  grounded in the #434 survey of 732 real published SR search strings (the
  dominant real-world shape is a flat AND of OR-groups over one field — which the
  old canonical shattered into per-group clauses).

### 3.3 Delimiters and the no-escaping result

| Delimiter | Meaning |
|---|---|
| `( … )` | boolean grouping: a group of clauses **and** a group of values/terms (`is (a or b)`, `has (a or b)`) |
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
works where title has apple and title has (banana or cherry)  (row 7)  ✓
works where title has apple and banana or cherry      (row 8)   ✗ OQL_UNDELIMITED_TERM_LIST
works where title has ("a" and "b" and "c")           (row 9)   ✓ (pure-AND, associative)
works where title has FOO and (bar or baz)            (row 10)  ✓ (any case accepted on input)
```

- **Operators always sit OUTSIDE quotes.** Inside quotes, even `or` is a literal
  word (§3.6 governing law).
- **`and` / `or` / `not` are lowercase canonically**, but **case-insensitive on
  input** (`AND`, `And`, `and` all parse). Lowercase wins on output because
  principle #1 is "reads aloud," and the rule "**`and`/`or`/`not` outside quotes are
  *always* operators — quote them to search them literally**" removes any ambiguity
  with content words, so the uppercase-for-disambiguation convention scholarly DBs
  rely on buys us nothing. (All keywords are lowercase: `where`, `is`, `has`,
  `within`, `stemmed`, `and`/`or`/`not`.)
- **`&` is an accepted input synonym for `and`** (`a & b` ≡ `a and b`, in both the
  clause body and inside a `has ( … )` search group). It is **input-only**: the
  canonical render always spells out `and`, never `&`. (Mirrors the long-standing
  `title & abstract` field-name spelling, which canonicalizes to `title/abstract`.)
- **Mixed and/or at one grouping level resolves by the standard precedence
  `NOT > AND > OR`** (oxjob #506) — it is **not** an error. `AND` binds tighter than
  `OR`, so `a and b or c` = `(a and b) or c` and `a or b and c` = `a or (b and c)`.
  This is the precedence boolean algebra and every programming language use, and —
  since Scopus changed early 2026 — **both Web of Science and Scopus now agree on
  it**, so honoring it (rather than throwing) matches the muscle memory of anyone
  coming from those tools. Pure-and or pure-or runs are associative and stay flat.
  **Canonical output always re-parenthesizes the precedence grouping**, so the
  structure is never left to the reader's head: the AND group inside a top-level OR
  renders parenthesized (`a or (b and c)`), while a single-connective level renders
  paren-free. (This reverses the pre-#506 rule, which raised
  `OQL_MIXED_BOOL_NEEDS_PARENS` and required hand-written parens — that code is
  retired.)
- **`not` is the prefix operator with the tightest precedence: it binds the single
  value immediately after it** (`not a or b` = `(not a) or b`). To negate a group,
  write `not (a or b)`. With AND/OR precedence now also in effect, the full operator
  ordering is the conventional `NOT > AND > OR`.
- **Adjacency (space) between *search words* = ONE value node, NOT AND** (§3.6, D2
  reversal #363): `title has (climate change)` is a single stemmed
  adjacency-boosted node, not climate AND change. At the top level a 2+ word value
  must still be parenthesized (`title has climate change` →
  `OQL_UNDELIMITED_TERM_LIST`, §3.6 row 17; the canonical render always
  parenthesizes). Explicit `and`/`or`/`not` build the tree *between* nodes, so
  `(climate change or warming)` = `node("climate change") OR node("warming")`.
  Explicit `and` + `or` at one level no longer errors — it resolves by precedence
  AND > OR (`(climate and change or warming)` = `(climate and change) or warming`),
  and the canonical render re-parenthesizes it. Between *whole
  clauses* at the top level a connective is still required (`year >= 2020 and
  open access is true`); two full clauses jammed together with no `and` is
  `OQL_IMPLICIT_ADJACENCY`. *(Adjacency-as-AND still holds for enum/value groups —
  §3.2 `country is (us and uk)`.)*

### 3.5 Negation — one mechanism

```
works where title has covid and abstract has not pediatric
```
→ `{title has covid}` AND `{abstract has pediatric, is_negated: true}`.

There is **one** negation mechanism, mapping to OQO's `is_negated` (NNF). On the
surface it is the bare prefix keyword **`not`**, written immediately before the
value it negates: `not FR`, `not dog`, `not col_abc`, `not unknown`. The predicate
spellings `is not` / `does not have` / `is not in collection` are **accepted on
input** as friendly aliases, but they are pure sugar — they lex straight to an
`is_negated` leaf (the OQO has no "negated predicate": its leaf operators are
strictly affirmative and negation only ever rides the `is_negated` bit), so they
**never survive canonicalization** — the emitted form is always the bare `not`
prefix.

**`not` binds the single value-node that follows it** — the tightest-binding
operator in OQL's `NOT > AND > OR` precedence (§3.4). A run of bare words is one
value-node (§3.6), so `not machine learning` negates the whole run. `not` binds only
the next operand: **`not a or b` = `(not a) or b`.** To negate a group, write
`not (a or b)`: the parens are an ordinary group and the canonicalizer pushes the
negation down to the leaves by De Morgan — `not (a or b)` → `(not a and not b)`.

`not`'s tight binding is the conventional top of the precedence ladder (§3.4), and
it is especially safe here because negation only ever applies to a **single value**
(canonical NNF never negates a whole clause — §3.2.2): in everything OQL *emits*
`not` always has exactly one value to its right, so there is no group for it to
ambiguously scope over. The **block builder** (the primary on-ramp) makes this
concrete — you negate an individual value brick, which prepends `not` to that one
chip; there is no affordance to negate a sub-clause. The OQL text matches the brick
1:1.

Canonical output pushes negation **down to the leaf/value** (NNF) and renders it as
a bare `not <value>` prefix — it **never** emits `not <whole clause>` (`not (country
is FR)` is a readability trainwreck, and the canonicalizer's NNF guarantees a
clause-level negation can't reach the surface). So:
- a **standalone** negated leaf: `country is not FR`, `title has not dog`,
  `work is in collection not col_abc`, `language is not unknown`;
- **in-group** negation prefixes each atom: `has (not a and b)`,
  `country is (not FR and US)` (§3.2.2).

**Booleans negate by flipping the value, not a `not` prefix** — a boolean's value is
just `true` or `false`, so the two polarities are `open access is true` /
`open access is false` (the builder toggles the value brick). `is not true` folds to
`is false` on input (§3.9). Negating a *group* value spells the same NNF either way:
`title has not (dog or cat)` and `title has (not dog and not cat)` both
canonicalize to `title has (not cat and not dog)` (two negated leaves on one
field merge — §3.2.2).

### 3.6 Search — the governing law

> **The search operator is `has`** (`title has cancer`). It was renamed from
> `contains` in #363 (charter decision 27 — shorter, friendlier, fits a monitor
> better) for both the OQL surface keyword **and** the OQO `operator` value, in
> lockstep. The old `contains` / `does not contain` spellings are a **hard error**
> (`OQL_CONTAINS_RENAMED`, with a `has` fix-it) — greenfield, no lenient parse,
> the same stance as decisions 23 & 24.

> **Stemming is ON by default; quotes are the only thing that turns it off.**
> A **run of bare words is ONE stemmed value node** (`(machine learning)` is one
> adjacency-boosted search, not `machine` AND `learning` — D2 reversal, #363); the
> engine matches each word across the field set (cross-field recall, #399) and
> ranks adjacency higher (`match_phrase` boost). **Explicit `and`/`or`/`not` build
> the boolean tree between such nodes.** **Quotes = an exact, adjacent phrase** (no
> stemming) — single word or many. **`stemmed "…"`** is the bridge: an adjacent phrase
> that *stays* stemmed (recall). A **quoted word embedded in a bare run** is an
> *escape* — a literal stemmed word — so a reserved word can sit inside a value
> (`road traffic safety "and" Ghana`). Outside quotes = structure; inside quotes =
> literal text (even `or` is just a word there).

This is the mainstream model (Google, Bing, PubMed, Web of Science, Elasticsearch
all do space=AND and quotes=exact), chosen after surveying peers — see the design
note in `plans/oqlo.md` and oxjob #330's research. OQO has exactly **one** text
operator, `has`; the *mode* is split across the **column** (stemmed vs exact
vs semantic) and **inline value micro-syntax** (phrase / proximity / wildcard); the
**boolean** structure is the filter tree.

> **Cross-surface note — quotes mean something different in the GUI search box.**
> In OQL, **quotes = exact** (a quoted value routes to `.search.exact`, no stemming).
> The openalex.org **search box** instead treats quotes as a **stemmed adjacency
> phrase**: a quoted query stays on the stemmed `.search` field (stemming is a
> separate explicit "Disable stemming" toggle, plus an unquoted wildcard auto-routes
> to exact). So the same `"climate models"` is an *exact* phrase typed into OQL but a
> *stemmed* phrase typed into the search box. Both surfaces are internally consistent
> and consistent with the engine; they simply chose different defaults for the quote
> character. The translator bridges them faithfully: a search-box (stemmed,
> quoted) URL — `title_and_abstract.search:"climate models"` — renders to OQL as
> **`stemmed "climate models"`** (stemmed adjacency), *not* `"climate models"` (which
> would be exact and return a different result set). This is intentional, not a
> translator bug. (oxjob #363, decided 2026-06-09: keep both, document the gap.)

| Axis | OQL surface | OQO encoding |
|---|---|---|
| field scope | the field name (`title`, `title/abstract`, `abstract`, `full text`, `raw affiliation`, `byline`) | column prefix (`display_name.search`, `title_and_abstract.search`, `fulltext.search`, …) |
| stemming | **default ON**; quotes turn it OFF | column suffix `.search` (stemmed) vs `.search.exact` |
| stemmed phrase | `stemmed "…"` | `.search` with a quoted value |
| semantic | `is similar to "…"` | column suffix `.search.semantic` (2-phase) |
| adjacency (phrase) | `" … "` | quotes in the value |
| proximity | `within N words` | `"phrase"~N` in the value |
| wildcard | bare `*` / `?` | `*` / `?` in the value |
| boolean | infix `and`/`or`/`not` inside `( … )` (a bare-word run is ONE node, not AND) | the BranchFilter tree |

The gauntlet pins the consequences (all are corpus rows):

| row | OQL (`title has …`) | Result |
|---|---|---|
| 11 | `(climate change)` | **a bare-word run = ONE stemmed adjacency-boosted node** (D2 reversal, #363; corpus row 126), NOT climate AND change. The everyday default. Use explicit `and` for two separate nodes (row 11 oqo). |
| 12 | `"climate change"` | **quotes = exact adjacent phrase**, no stemming (`.search.exact`) |
| 13 | `stemmed "whopper junior"` | **`stemmed` = stemmed adjacent phrase** → matches "whoppers junior" |
| 14 | `"cat"` | quoting a **single** word = exact (no plurals) — quotes always mean exact |
| 15 | `cat` | bare word = stemmed (matches cats) — a single bare term is fine |
| 16 | `"rock or roll"` | inside quotes = literal: `or` is a word, one exact phrase |
| 17 | `climate change or warming` | ✗ `OQL_UNDELIMITED_TERM_LIST` — 2+ bare terms must be parenthesized |
| 18 | `(climate and change or warming)` | ✓ resolves by precedence → `(climate and change) or warming` (canonical re-parenthesizes) |
| 19 | `"bar*"` | ✓ quoted wildcard = the sanctioned path → no-stem `.search.exact` (oxjob #364) |
| 20 | `bar*` | ✗ `OQL_WILDCARD_NEEDS_EXACT` — bare wildcard is stemmed (wrong); fix-it: quote it `"bar*"` |

Key rules these encode:

- **A single bare term is fine; a 2+ word value must be parenthesized at top level**
  (the arity rule, §3.2). `title has cancer` ✓; `title has climate change` →
  `OQL_UNDELIMITED_TERM_LIST` (row 17) — this is the rule that kills the silent
  keyword-truncation footgun. **Inside a `( … )` group** a bare-word run is ONE node
  (D2 reversal, #363), so `(climate change or warming)` = `node("climate change") OR
  node("warming")`. **Mixing explicit `and` and `or` at one level resolves by the
  standard precedence AND > OR** (#506) — `(climate and change or warming)` =
  `(climate and change) or warming`; the canonical render re-parenthesizes it so the
  grouping is always explicit. (Pure runs — all-`and` or all-`or` — stay flat with no
  inner parens.) A literal reserved word inside a value is quoted as an escape
  (`("road traffic" "and" ghana)` style — §3.6 governing law).
- **Quotes = exact, single word or phrase.** `"cat"` excludes "cats"; `"climate
  change"` is the adjacent, unstemmed phrase. This is the mainstream "quotes = exact
  match" people already expect.
- **`stemmed "…"` = the stemmed phrase** — adjacent *and* lemmatized (`.search`), for
  when you want phrase precision without losing recall (corpus rows **13**, **32**).
  Without quotes you don't need `stemmed`: bare terms are already stemmed.
- **Booleans are structural, never lexical.** `has "foo or bar"` searches the
  literal phrase; the boolean is the tree (`has (foo or bar)`).
- **`is similar to "…"` is semantic** vector search (`.search.semantic`, corpus
  row **30**).
- **A `( … )` group holds a boolean of terms** — canonical `has (a and (b or c))`;
  items may themselves be `"exact"` or `stemmed "phrase"` phrases. Groups nest freely
  (§3.2).
- **A search value runs until the next field-clause.** `title has (a or b) and
  year >= 2020` is `(title has (a or b)) and year >= 2020` — the `or` is the
  has-group's, the `and` joins clauses. This is deterministic, not a precedence
  choice: a `year >= …` clause can't live *inside* a `has`, so the value
  boundary is forced. A genuinely mixed and/or *between clauses* resolves by
  precedence AND > OR (§3.4).

### 3.7 Proximity and wildcards — the edge matrix

```
works where title has "smart phone" within 3 words      (row 21) ✓ exact proximity → .search.exact "smart phone"~3
works where title has stemmed "smart phone" within 3 words (row 32) ✓ stemmed proximity → .search "smart phone"~3
works where title has "foo*bar"                        (row 22) ✓ mid-word * (quoted = no-stem .search.exact)
works where title has "wom?n"                          (row 23) ✓ ? = exactly one char (quoted = no-stem)
works where title has bar*                             (row 20) ✗ OQL_WILDCARD_NEEDS_EXACT (bare = stemmed = wrong)
works where title has *cycle                           (row 24) ✗ OQL_LEADING_WILDCARD
works where title has ?cycle                           (row 25) ✗ OQL_LEADING_WILDCARD
works where title has ab*                              (row 26) ✗ OQL_SHORT_WILDCARD_PREFIX (need ≥3)
works where title has "smart phone*" within 3 words    (row 27) ✓ wildcard-in-proximity → ES intervals (oxjob #355)
works where title has "smart" within 3 words of "phone"(row 28) ✗ OQL_BINARY_PROXIMITY
works where title has smart* within 3 words            (row 29) ✗ OQL_WILDCARD_IN_PROXIMITY
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
  single `has` leaf expresses intra-affiliation co-occurrence (corpus rows **65**,
  **75**, **77**).
- **Wildcards require the no-stem (exact) field — quote them (oxjob #364).** A
  wildcard matches indexed tokens literally, but the default search is *stemmed*
  at index time, so a bare wildcard hunts for a prefix the index no longer holds
  and returns near-nothing (`studies*` = 2.4k stemmed vs 2.2M no-stem). So a wildcard
  on a single token must be **quoted** → it runs on `.search.exact`: `"bar*"`,
  `"foo*bar"`, `"wom?n"`. A **bare** wildcard is `OQL_WILDCARD_NEEDS_EXACT` (fix-it:
  quote it). `stemmed` keeps a phrase stemmed, so a wildcard there is the same error.
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
> phrase/proximity* is gapped, and you can often sidestep it with `has x and
> y*` when the words needn't be adjacent.

### 3.8 `null` / `unknown`

`language is unknown` / `language is not unknown` → `value: null` (± `is_negated`).
Emit `unknown` canonically; accept `null` and `unknown` on input.

### 3.9 Booleans (`<flag> is true|false`)

Boolean (yes/no) columns are ordinary subject-predicate-value clauses, exactly like
every other filter — the subject is the flag's noun and the only values are `true`
and `false`: `open access is false`, `retracted is true`, `has DOI is true`,
`has ORCID is true` (corpus rows **37**, **40**, **50**, **53**). They compile to
`{column: …, value: true|false}`. `is not true` / `is not false` are accepted on
input and fold into the value, so the canonical form is always `is true` / `is false`
(never a separate `not`). The old reads-aloud `it's …` / `it has …` surface was
removed in #363 — there is now One Right Way, shared with all other clauses.

The flag's noun drops any helper verb (`is_retracted` → `retracted`,
`open_access.is_oa` → `open access`); where the bare noun would collide with a
value-bearing field it keeps a short `has` qualifier (`has DOI`, `has ORCID`,
`has abstract`, `has ISSN`) so `DOI is …` stays the exact-DOI string filter.

### 3.10 Collection membership: `is in collection`

```
works where work is in collection col_abc123                       (same-type: works in a Collection of works)
works where author is in collection col_xyz789                     (cross-type: works by authors in a Collection of authors)
works where country is in collection col_eu27                      (row 5x — predefined country set)
works where work is in collection not col_abc123                   (negation: bare not prefix on the value, §3.5; is not in collection accepted on input)
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
works where year >= 1976 group by topic, year              (row 48)  (multi-dim: spec-level; live API single-dim → #297)
works where … stemmed "genome editing" … sample 500                (row 63)
```

- **`group by <dim>[, <dim>]*`** → `group_by` list (order = dimension order).
- **`sample <n> [seed <s>]`** → `sample` (+ optional reproducibility `seed`).

**Not in the OQL surface (oxjob #504):** result *sort order* (`OQO.sort_by`) and
*column projection* (`OQO.select`) are display concerns, not query language. They
are populated by the URL (`?sort=` / `?select=`) and the GUI's own sort dropdown /
column picker, and round-trip through OQO untouched — OQL simply never reads or
emits them. (They are additive to re-introduce in a future OQL version.)

## 5. Diagnostics (codes + fix-its)

Diagnostics are a **language-agnostic contract** (charter decision 5): every error
is a stable **code** + a human message + a **fix-it**; consumers (parser, editor,
NL) share codes and only localize prose. Every `✗` corpus row asserts its code.

| Code | When | Fix-it |
|---|---|---|
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
| `OQL_BAD_SAMPLE` / `OQL_BAD_PROXIMITY` / `OQL_PROXIMITY_NEEDS_PHRASE` / `OQL_SEMANTIC_NEEDS_TEXT` / `OQL_TRAILING_TOKENS` | malformed directive/clause | — |

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
| `domains`     | numeric id (4 total)     | `2` / `99999`, `social sciences` |
| `fields`      | numeric id (26 total)    | `27` / `99999`, `medicine` |
| `subfields`   | numeric id (252 total)   | `2712` / `99999` |

> The topic-hierarchy vocabs (`domains` / `fields` / `subfields`) are small,
> fully-enumerable closed sets, so they validate the same way: `field is 99999`
> (out-of-range) and `field is medicine` (a name) are rejected, with a "did you
> mean '27'?" fix-it for the name. (Tier 1.5, oxjob #363.)

> `gb` is the ISO code for the United Kingdom; `uk` is **not** a valid code and is
> rejected (the NL phrasings "UK"/"Britain"/"United Kingdom" all resolve to `gb`).

Membership descends into value groups, so each leaf of `country is (us or canada)`
is checked independently. Free-text `*.search` / `phrase` values and raw strings are
never membership-checked.

### 6.2 ID-shape validation (open ID entities)

The **open** ID entities — authors, works, institutions, sources, publishers,
funders, topics, concepts, awards — have millions of members, so they can't be
enumerated. Instead, an `openalex_id`-typed value is checked for the right
**ID prefix/shape** for the column's `entity_type`. This catches the common slip of
a correctly-shaped ID of the *wrong* type: `institution is W5` is an `invalid_value`
error — `W5` is a Works ID, and `institution` expects an Institutions ID (`I…`). A
non-ID value on an ID column (`institution is Canada`) is likewise rejected.

The shape is **declared once**, in each entity's `idRegex` in
`config/<entity>.yaml` (the same files the renderer reads for closed-vocab names),
surfaced as a typed registry in `core/entities.py` — the server-side sibling of the
properties registry, the thing a `Property.entity_type` resolves against. There is
no hand-maintained prefix table: the native-entity set and their prefixes are
derived from those `idRegex`. The OpenAlex URL/path forms a value may legitimately
take (`I5`, `institutions/I5`, `https://openalex.org/I5`) all validate; only the
entity letter is enforced.

| `entity_type` | prefix | `entity_type` | prefix |
|---|---|---|---|
| `works` | `W` | `funders` | `F` |
| `authors` | `A` | `topics` | `T` |
| `institutions` | `I` | `concepts` | `C` |
| `sources` | `S` | `awards` | `G` |
| `publishers` | `P` | | |

> `is in collection col_…` uses a distinct operator (not `is`), so a `col_…` value
> on an ID column is **not** shape-checked. Slug-id entities (`keywords`) and
> numeric-id entities (`fields` / `subfields` / `domains`) have no letter prefix and
> are not shape-checked here.

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
computing` (row 72) etc. render as bare terms. A genuine adjacent phrase uses `stemmed
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
- [`oql-addressing.md`](./oql-addressing.md) — decimal addressing (outline
  coordinates `1`, `3.1`, `4.1.2`) over this filter tree, for diagnostics, the
  builder, and human reference (oxjob #474). Additive; changes no language surface.
- [`oql/corpus.yaml`](./oql/corpus.yaml) — the normative cases.
- [`oql/gap_report.md`](./oql/gap_report.md) — v1.1 → v2 work-list.
- [`oql/engine_findings.md`](./oql/engine_findings.md) — engine reality behind the
  wildcard/proximity errors.
- `plans/oqlo.md` (oxjobs) — the OQLO charter (architecture, roadmap, decisions).
