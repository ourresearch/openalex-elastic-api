# OQL v2 — engine reality vs. spec (oxjob #330)

The OQL v2 spec only promises what the ES engine can actually execute (charter
decision 2: never promise what OQO can't execute). This file records the engine
behavior that shaped the spec's wildcard/proximity error cases, plus the open
discrepancies to file as engine work. Verified 2026-06-01 against
`openalex-elastic-api/core/search.py`.

## Wildcard detector

`SearchOpenAlex.has_wildcard()` (`core/search.py:371`):

```python
re.search(r'\w{3,}\*|\*\w{3,}|\w\?\w|\w{3,}~|"~', terms)
```

Every query path hard-sets **`allow_leading_wildcard=False`**.

| Pattern | `*` (zero-or-more) | `?` (exactly one) |
|---|---|---|
| trailing `foo*` | ✅ needs ≥3-char prefix | ✅ if a word-char precedes |
| mid-word `foo*bar` / `f?o` | ✅ within one token | ✅ one slot, word-char both sides |
| leading `*cycle` / `?cycle` | ❌ blocked (perf landmine) | ❌ not even detected |

- `?` = **exactly one** char (not `*`'s zero-or-more): `foo?bar` matches "fooXbar",
  not "foobar".
- Wildcards match **within a single token** (won't cross whitespace).

The spec turns each unsupported shape into a loud diagnostic (corpus rows 24–29):
`OQL_LEADING_WILDCARD`, `OQL_SHORT_WILDCARD_PREFIX`, `OQL_WILDCARD_IN_QUOTES`,
`OQL_WILDCARD_IN_PROXIMITY`, `OQL_BINARY_PROXIMITY`.

## Open discrepancies to file as engine work

These are **not** spec gaps — they are places the live engine violates "loud, never
silent" or contradicts code that says a feature works. Filed as oxjob stubs off
this job; listed here so the spec's `✗`/`⚠` decisions are traceable.

1. **Trailing-wildcard `500` (corpus row 57).** The code *supports* `foo*`, yet
   `title_and_abstract.search:phone*` was observed `500`-ing on the live server
   (2026-05-30, "not yet shipped"). The spec marks `phone*` ✅; the gap report
   flags the live 500 as `ENGINE-BUG`. **Fix on the engine, don't spec around a
   moving target.**

2. **Sub-3-char prefix silently isn't a wildcard.** `ab*` doesn't match the
   detector, so the `*` is silently treated as a literal — a silent wrong answer.
   The spec rejects it (`OQL_SHORT_WILDCARD_PREFIX`); the engine should also stop
   silently degrading.

3. **Leading `*`/`?` surfaces as a raw ES error, not a friendly message.**
   `allow_leading_wildcard=False` makes ES throw; the user sees a 500/stack, not
   "leading wildcards aren't supported." The spec rejects up front
   (`OQL_LEADING_WILDCARD`); the engine path should fail friendly too.

4. **`?`/`*` that don't match the detector shape silently become literal.** Same
   class as (2): any near-miss of the detector regex is a silent degradation.

## Acknowledged capability gap: wildcard-in-a-phrase / near another word

`"unusual behavi*or"`, `"smart phone*" within 3 words` — a wildcard combined with a
phrase or proximity — is **rejected today** (corpus rows 27, 29, 58) because our ES
`query_string` path **silently drops the wildcard** (row 58 verified live 2026-05-30).
This is an **acknowledged limitation, not a permanent boundary**: **WoS and Scopus
support it**, so it's a real gap vs. the big scholarly DBs. ES *can* express
"wildcard term near another term" with heavier query types (**intervals** queries,
or `span_near` + `span_multi(wildcard)`) — just not in the simple query path we use.

- A wildcard **on its own word** (`behavi*or`, UK/US spelling) works fine today; only
  the *combination* with a phrase/proximity is gapped.
- Often sidesteppable: if the words needn't be adjacent, `contains unusual and
  behavi*or` works.
- Closing it is future engine work — exactly what the "lift to structure"
  recommendation below enables (adjacent to #298 nested mapping / #337 wildcards).
  The OQL spec marks it a loud, named error today so we never silently mislead.

## Recommendation back to OQO / engine (not in scope for #330)

Consider lifting proximity / wildcard / adjacency **out of the opaque `value`
string into structure** — a typed modifier on the search leaf (e.g.
`{contains, term, mode: phrase|exact|semantic, proximity: N, wildcard: bool}`)
instead of an ES mini-language re-parsed by every surface. Today every renderer/
parser (OXURL, OQL, NL, chips) must agree on the `"phrase"~N` / `*` / `?`
micro-syntax inside the value; structure would make the hub authoritative and the
surfaces trivial. Keeps the OQO core rock-solid (charter §1). Tracked as a
follow-up, adjacent to #298 (nested affiliation mapping).
