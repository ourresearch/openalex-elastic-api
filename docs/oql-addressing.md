# OQL clause addressing — decimal coordinates over the filter tree

> **Status: spec, under review** (oxjob #474). Additive layer over the **frozen**
> v2 language ([`oql-spec.md`](./oql-spec.md)); it adds *no* language surface and
> changes no parsing/rendering behavior. This is a cases-first spec like its
> parent: the worked examples in §6 are the normative truth; the prose is the
> generalization under them.

## 1. What this is and why

OQL filter trees nest: cross-field clause groups, within-field value groups, and
negated leaves. There is no human-sayable way to point at one node — "the third
synonym in the title block", "that nested OR group", "the clause the error is on".

**Clause addressing** assigns every meaningful node in the canonical OQL filter
tree a short **outline decimal address** (`1`, `3.1`, `4.1.2`) — the same scheme
legal documents and ISO standards use for nesting. Three consumers:

1. **Debugging / diagnostics** — an error can name the offending node by address
   (GraphQL `errors[].path` style), instead of echoing a fragment of text.
2. **The no-code builder** — show nesting with a stable gutter; "edit node `3.1`".
3. **Humans talking to humans** — a shared vocabulary for discussing a query.

Addresses are a **pure, deterministic function of the tree** — the same traversal
the renderer already walks. They are **positional coordinates, not durable IDs**:
they describe where a node *is*, and they change when the tree is edited (§5).

## 2. The tree being addressed (the one rule that matters most)

Addresses attach to the **canonical OQL merged render tree** — `oql-spec.md`
[§3.2.2](./oql-spec.md), where all same-`(field, base-operator)` structure merges
into **one** clause with the boolean tree living *inside* the value group. They do
**not** attach to the OQO, which is maximally distributed (NNF, field re-stated on
every leaf): in OQO, `title has ((vape or vaping) and (health or harm))` is four
sibling leaves; in canonical OQL it is one clause with a nested value tree, and the
user's worked addresses (`1.1.2`, `1.2.1`, …) only exist in the merged shape.

Concretely, this is exactly the tree produced by
**`query_translation/oql_render_v2.build_tree(oqo, resolver)`** (oxjob #428) — an
OQO-faithful node tree whose value sub-clauses are *real nodes* (`vgroup` /
`vleaf`) and whose every node already carries an opaque id. Addressing is a pure
walk of that dict (§7). Because that tree *is* the §3.2.2 merged form, "address the
canonical OQL, not the OQO" is satisfied by construction.

Operand order is the user's ([oql-spec §1, decision 30](./oql-spec.md)) on the
OQL/builder path, so an address both is structurally stable and **matches what the
user sees and reads aloud**. The canonicalizer also unwraps single-child groups and
forbids redundant `(…)` levels, so no spurious wrapper level ever appears in an
address.

## 3. The numbering rules

Outline style, **1-indexed**, with a reserved `.0` "head" segment per node. The
whole `where` clause is one **implicit root group**, addressed like any other
group.

| Node                                        | Address                                            |
|---------------------------------------------|----------------------------------------------------|
| **Root conjunction** (the implicit top-level join) | `0`                                         |
| **Top-level clauses**                       | `1`, `2`, `3`, … (in user order)                    |
| **Cross-field clause group** (`group`)      | node `N`; `N.0` = its join (`and`/`or`); children `N.1, N.2, …` |
| **Leaf clause** (`clause`)                  | node `N`; `N.0` = the field/column; value(s) `N.1, N.2, …` |
| **Value group** (`vgroup`, nested)          | node `A`; `A.0` = its join; children `A.1, A.2, …`  |
| **Value atom** (`vleaf`, scalar)            | a numbered leaf `A`                                 |

Five consequences worth stating explicitly:

- **The root is just a group.** `0` is its head — the conjunction joining the
  top-level clauses (always `and` in current OQO, since the top level is an
  implicit AND of `filter_rows`). This makes the root behave identically to every
  nested group (`.0` = join, children `.1, .2…`) and gives the top-level connective
  a coordinate it otherwise lacked. A query with a **single** top-level clause has
  no root conjunction, so it has no `0` and starts at `1` (same as the canonicalizer
  unwrapping a single-child group).
- **The entity is not addressed.** `works` is the query's *subject* (`get_rows`),
  not a node in the filter tree, so it carries no decimal address. There is only
  one; "the entity" names it.
- **`.0` is always the node's *head*** — a group's connective, a leaf's field. It
  is never a child.
- **Leaf ↔ value-group fusion.** A leaf whose value is a group does **not** get an
  extra level for the group: the group's operands become the leaf's `.1, .2, …`
  directly. So `full text has ((dog or cat) and (play or jump))` →
  `4.0` = `full text`, `4.1` = `(dog or cat)`, `4.1.2` = `cat`, `4.2` =
  `(play or jump)`. A single-value leaf (`type is article`) and a group-value leaf
  number identically (`3.2.1` = `article`); deeper trees just nest deeper.
- **Number what's a distinct token in the rendered OQL string.** A leaf's `.0`
  (field) and `.1, .2…` (values) exist because they are separately-rendered tokens:
  - search text / entity ID / enum / numeric bound / collection → field token at
    `.0`, scalar value token at `.1` (`title has animal` → `1.0` = `title`,
    `1.1` = `animal`; `country is in collection col_eu27` → `1.1` = `col_eu27`);
  - **null / `is unknown`** → `.0` = field, `.1` = `unknown` (both are tokens in the
    string: `DOI` … `unknown`); `is not unknown` keeps `.1` = `unknown` and rides
    the `not` as an attribute, like any other negated leaf.
- **A boolean flag is one atomic node — no `.0`, no `.1`.** OQL renders a boolean as
  a single fused phrase that mixes the property *and* its value into one
  inseparable string: `it's open access`, `it doesn't have a DOI`. There is no field
  token and no value token to point at, so the clause is just `N`, with no children.
  (The underlying `open_access.is_oa = true/false` lives in the OQO, **not** the OQL
  string — and addresses name what's in the *string*, so the true/false gets no
  address. This is the one leaf kind with no `.0`.)

### What is NOT numbered (node attributes, not nodes)

This is **semantic line-numbering, not a tokenizer.** The following are *attributes*
of a numbered node, carried on it, never addressable in their own right:

- **Parentheses** — structure, implied by depth.
- **Operators** — `has` / `is` / `>=` / `in collection` (an attribute of the leaf).
- **Negation** — `is_negated` / a bare `not` prefix (an attribute of the leaf,
  value atom, or group it sits on; NNF means it usually rides a `vleaf`). For a
  **boolean**, the polarity is baked into the fused phrase itself (`it's not open
  access`), which is atomic — so there's nothing separate to mark either way.
- **The value-root join.** The join of a leaf's *top* value group is an attribute
  of the leaf, **not** an addressed `.0` — because `.0` is already taken by the
  field. So in `title has (A and B)` the value-root `and` rides on the leaf; but a
  **nested** value group keeps its `.0` join normally (`4.1.0` = `or` above). This
  asymmetry is the one wrinkle: the top value join is special only because the
  field owns the leaf's `.0`.

## 4. Internal representation: a list of ints; display is dotted, semver-style

The **canonical / wire** address is a **list of integers** — `[3, 1, 2]` — exactly
the shape of GraphQL `errors[].path`. It is the right form for programmatic path
access and lookups (§6).

The **display** form is dotted, **always** — `3.1.2`, `1.10`, `1.13.42` — like
semver. There is **no special case at ten**: the dots are delimiters, so `1.10` is
unambiguously the tenth child (`[1, 10]`), never `[1, 1, 0]` (which is written
`1.1.0`). Real systematic-review synonym blocks of 100+ items number straight
through — `1.114` is fine. (An earlier draft fell back to an array rendering past
nine; that was unnecessary — semver shows multi-digit dotted segments are
unambiguous given the delimiter.)

## 5. Addresses are coordinates, not IDs

An address answers "where is this node?", computed fresh from the tree on every
render. It is correct for display, debugging, and verbal reference. It is **not** a
durable identity: inserting a clause renumbers its siblings, so an address must not
be persisted and later resolved against an edited tree, or used as a stable key.
(The v2 tree's opaque `id` (`n1`, `n2`) remains the within-a-render handle; see §7
— addressing rides *alongside* it.)

## 6. Lookup shape returned to consumers

The traversal (§7) produces both, from one walk:

- **Per-node stamp** — each node gains an `addr` field = its int list (alongside,
  not replacing, the existing opaque `id`). Renderers/builders read it in place.
- **Flat map** — `{ tuple(addr): node }` for O(1) "what is at `[3,1,2]`?" lookups
  (diagnostics, "edit node N").

Engine behavior: addresses appear **only in debug / error contexts** (an
`errors[].path` int list on the offending node) — **never** in the normal query
payload, where they are derivable and would only bloat the response.

## 7. Out of scope

- **`group by`** — a flat ordered list; list position already *is* the
  meaning. No hierarchical numbering. (`sort`/`select` are not in the OQL surface —
  oxjob #504.)
- **The v1.1 ↔ v2 reconciliation** — moot here: oxjob #376 collapsed the two into
  one engine (`query_translation/oql_lang.py`); `tests/oql/oql_v2.py` is a thin
  re-export. Addressing attaches to the single `oql_render_v2` tree.
- **Builder block-layout (#428)** — addressing aligns with canonical OQL, so the
  builder gutter is expected to fall out of this; tracked there, not here.

## 8. Conformance cases (normative)

Verified against `oql_render_v2.build_tree` on 2026-06-17 (oxjob #474). In Phase 2
these become `addr:`-annotated rows in [`oql/corpus.yaml`](./oql/corpus.yaml) plus
a machine checker; until then this table is the oracle.

### Case A — the full worked example (root conjunction, boolean, merged, nested)

```
works where title has animal
  and it's open access
  and (institution is (I33213144 or I97018004) or type is article)
  and full text has ((dog or cat) and (play or jump))
```

| addr | node |
|------|------|
| *(unaddressed)* | entity `works` — the query subject, not a filter node |
| `0` | root conjunction `and` |
| `1` | `title has animal` |
| `1.0` | field `title` |
| `1.1` | `animal` |
| `2` | `it's open access` *(atomic — boolean, no `.0`/`.1`)* |
| `3` | cross-field group |
| `3.0` | `or` |
| `3.1` | `institution is (…)` |
| `3.1.0` | field `institution` |
| `3.1.1` | `I33213144` |
| `3.1.2` | `I97018004` |
| `3.2` | `type is article` |
| `3.2.0` | field `type` |
| `3.2.1` | `article` |
| `4` | `full text has (…)` |
| `4.0` | field `full text` |
| `4.1` | `(dog or cat)` |
| `4.1.0` | `or` |
| `4.1.1` | `dog` |
| `4.1.2` | `cat` |
| `4.2` | `(play or jump)` |
| `4.2.0` | `or` |
| `4.2.1` | `play` |
| `4.2.2` | `jump` |

### Case B — a boolean flag is one atomic node

```
works where it's open access and it doesn't have a DOI
```

| addr | node |
|------|------|
| `0` | `and` |
| `1` | `it's open access` *(atomic — no `.0`/`.1`)* |
| `2` | `it doesn't have a DOI` *(atomic — no `.0`/`.1`)* |

Each flag is a single fused phrase in the OQL string, so it is one bare address with
no children — the property and its true/false are inseparable in the text. A
single-flag query (`works where it's open access`) has one top-level clause and is
just `1` (no `0`, no children).

### Case C — merged single clause, NOT four distributed rows

```
works where title has ((vape or vaping) and (health or harm))
```

One top-level clause `1` (`1.0` = `title`), with a nested value tree
(`1.1`/`1.1.0`/`1.1.1`/`1.1.2`, `1.2`/`1.2.0`/`1.2.1`/`1.2.2`) — **not** four
sibling rows. The OQL-vs-OQO discriminator. (Single clause ⇒ no root `0`.)

### Case D — past ten is no special case (semver-style)

```
works where title has (Boy or Girl or Minors or … or youths or schoolboy)
```

The 10th–12th synonyms are `1.10` / `1.11` / `1.12` — plain dotted. `1.10` is the
tenth child (`[1,10]`), unambiguous because the dot delimits; `[1,1,0]` would be
written `1.1.0`. A 114-leaf block runs straight to `1.114`.

### Other verified shapes

- **Negated set** `institution is (not I33213144 or not I97018004)`: `1.0` =
  `institution`, `1.1` = `not I33213144`, `1.2` = `not I97018004` (negation is an
  attribute of each value atom; the value-root `or` rides the leaf, unaddressed).
- **Numeric two-bound range** `year >= 2019 and year <= 2023`: `0` = `and`, then
  **two** clauses — `1` (`1.0` = `year`, `1.1` = `2019`) and `2` (`2.0` = `year`,
  `2.1` = `2023`) — because different comparators never merge (§3.2.1).
- **Null** `doi is unknown`: `1` (single clause, no `0`), `1.0` = `DOI`, `1.1` =
  `unknown`.

## 9. Related documentation

- [`oql-spec.md`](./oql-spec.md) — the frozen v2 language; §3.2.2 is the merged
  render tree these addresses attach to.
- [`oqo-spec.md`](./oqo-spec.md) — the canonical query object (the distributed
  shape addresses deliberately do *not* use).
- [`oql/corpus.yaml`](./oql/corpus.yaml) — normative cases; gains `addr:` rows in
  Phase 2.
- `query_translation/oql_render_v2.py` — `build_tree`, the tree addressing walks.
- `plans/oqlo.md` (oxjobs) — the OQLO charter.
