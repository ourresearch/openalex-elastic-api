# Versioning the `/properties` contract

> **Dear agent / human:** `/properties` (and `/entities/{entity}/properties`) is a
> **public contract** — the Python and JS OQLO libs bundle a frozen copy of it
> (`docs/properties-snapshot.json`), and its `fingerprint` is used as a cache-bust
> key. If your change alters the rendered payload, CI will block until a human bumps
> `PROPERTIES_VERSION` to match the change class. **Do not bump it yourself — flag the
> human in the loop (Jason or Casey) to approve.**

## What this covers

`PROPERTIES_VERSION` (in `core/properties.py`) is the human-curated semver of the
entity-property catalog served at `/properties`. It is surfaced as `meta.version` in
the payload and the committed snapshot.

The catalog is a derived **projection** of the live `Field` objects (each entity's
`fields_dict`). Any change to those fields — adding/removing a field, changing its
`field_type`, its `operators`, its `actions`, or its cross-type `entity_type` — changes
the rendered payload and therefore the `meta.fingerprint`.

## The bump rule

| Change | Bump |
|---|---|
| Add an entity, property, operator, action, or selectable field | **MINOR** |
| Add or tweak a property's `display_name` (#381 — a label is display metadata, not query semantics) | **MINOR** |
| Add an `alias` (#381 — an extra accepted input spelling) | **MINOR** |
| Remove any of the above; rename a property/param; change a property's `type`; change an `entity_type` cross-link; drop an operator/action | **MAJOR** (breaks existing queries) |
| Remove a `display_name` or an `alias` (#381 — dropping an alias can invalidate a query a client was sending) | **MAJOR** |

**Rule of thumb:** could a query that was valid yesterday become invalid or change
meaning after your change? → **MAJOR**. Purely additive? → **MINOR**.

There is **no PATCH lane** — the `fingerprint` already records that *something* changed,
so a third number would carry no information.

## How the gate enforces it

The CI drift gate (Phase 3) runs on push to `master`:

1. **Staleness** — re-renders the catalog and asserts it byte-matches the committed
   `docs/properties-snapshot.json` (`python scripts/render_properties.py --check`).
   Fails if you changed a `Field` but didn't regenerate the snapshot.
2. **Bump match** — diffs the committed snapshot against its git base, classifies the
   diff (added ⇒ minor / removed|type|operator|action|rename ⇒ major), and asserts the
   `PROPERTIES_VERSION` delta matches the change class. Fails with the diff + the
   required bump + a link to this doc otherwise.

This is mechanical on purpose — "remember to bump it" comments are exactly the
silent-drift failure mode (#294) this job exists to remove.

## When you change the catalog

1. Regenerate the snapshot: `python scripts/render_properties.py` (from repo root,
   `PYTHONPATH=.`).
2. **Flag a human** (Jason or Casey) with the change class. They bump
   `PROPERTIES_VERSION` in `core/properties.py`.
3. Commit the field change, the regenerated snapshot, and the version bump together.
