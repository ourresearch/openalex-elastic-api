"""Entity properties (#331; formerly the column registry, #294 Phase B) —
build-at-boot, in-memory.

A per-entity catalog of every queryable property, derived from the SAME live
`Field` objects the filter layer executes (each entity's `fields_dict`). Built
once at import by calling `Field.to_property()` on every field, so this catalog
and the executor can never disagree.

"Registry" was a backwards name: nothing *registers* into this — it is a derived
**projection** of the live `Field` objects (the real source of truth). It is a
read-only computed view; editing it does nothing. Hence the #331 rename to
"properties" (a catalog of each entity's queryable properties).

    ENTITY_PROPERTIES[entity_type][property_name] = Property(...)

`entity_type` keys are the OQO `get_rows` strings (hyphenated where the OQO uses
hyphens, e.g. "work-types") so a caller can look up `ENTITY_PROPERTIES[oqo.get_rows]`
directly. `property_name` keys are each field's `param` — the same space the OQO's
`LeafFilter.column_id` and `core.utils.get_field` resolve against.

Consumers: the OQO validator (`query_translation/validator.py`) and the
`GET /properties` endpoint (plus the deprecated `/registry` aliases). The offline
audit tool (`oxjobs/.../check_client_subset.py`) cross-checks against this. This
module — introspecting the live objects — is the runtime source of truth; the
committed `docs/properties-snapshot.json` is its versioned, fingerprinted mirror.
"""

import hashlib
import importlib
import json
from dataclasses import replace

from core.display_names import resolve_display_name
from core.fields import Property

# Human-curated semver of the published /properties contract (#331 Decision C).
# MINOR/MAJOR only — no PATCH lane (the fingerprint already records that the
# payload changed). Bumped by a human (Jason/Casey) when the rendered payload
# changes; agents MUST NOT self-bump — flag the human. The CI drift gate ties
# this constant to the change class. See docs/PROPERTIES_VERSIONING.md.
# 1.3.0 (#381): added display_name + aliases to each property (purely additive).
# 1.4.0 (#381 Phase 4): reconciled display_name labels with the GUI (de-paren, GUI-wins,
# is_xpac→"in extended index", #374 works-search labels, alias-param fold-in). Label
# edits = MINOR (no query breaks).
# 1.5.0 (#381 consistency gate): unified the citation/reference family to field-standard
# labels — cited_by_count "citation count" (singular, all entities), referenced_works
# "references", referenced_works_count "reference count" (old spellings kept as aliases).
# Jason-approved 2026-06-07. Label edits = MINOR.
# 1.6.0 (#381 Phase 5): sustainable_development_goals.id label "sustainable development
# goal" → "SDG" (canonical acronym everywhere — registry/GUI/OQL; long forms kept as
# aliases). Jason-approved 2026-06-07. Label edit = MINOR.
# 1.8.0 (#394): every registry entity is collectible (minus locations) — ~30 filter
# properties (countries/continents/languages/licenses/oa-statuses/source-types/
# institution-types/work-types/domains/fields/subfields/awards params, + bare `type` on
# works/sources/institutions) gained `entity_type`. Purely additive (property_count and
# entity_count unchanged). Jason-approved 2026-06-08. = MINOR.
# 1.9.0 (#402 friendly-name audit): curated display_names for long-tail works columns that
# previously rendered the raw humanized column id — batch: biblio.{volume,issue,first_page,
# last_page} → volume/issue/first page/last page; ids.{mag,pmid,pmcid} → MAG ID/PMID/PMCID.
# Net-new curated labels on raw columns (no already-shipped label changed). Jason-approved
# (blanket MINOR for this job) 2026-06-08. = MINOR.
# 1.10.0 (#402 friendly-name audit): batch 6 location/OA mirror string/id cols — curated
# display_names for the best_oa_location.* / locations.* / primary_location.* source id/issn/
# type, license, and version mirrors (matrix scope words: primary unmarked / "best OA …" /
# "any location …"). Resolves the live best_oa_location.license vs locations.license duplicate
# "license" (primary now owns bare "license"). Net-new labels (no already-shipped label
# changed). Jason-approved (blanket MINOR for this job). = MINOR.
# 1.11.0 (#406 OQL multi-entity): corrected the `ids.openalex` display_name on the six
# non-works entities (authors/sources/institutions/topics/publishers/funders) + concepts
# from the singular entity name ("author"/"source"/…) → "openalex id" (matching works + the
# GUI id facet); the entity-name labels were inaccurate and made the entity's own name
# wrongly resolve to its id. Added "subfield" as a parse alias on topics `subfield.id`
# (display_name stays "parent subfield"). display_name tweak + alias add. Jason-approved
# 2026-06-09. = MINOR.
PROPERTIES_VERSION = "1.11.0"

# ┌─ AGENT/HUMAN: keep in lockstep with query_translation/views.py:_resolve_entity ─┐
# │ OQO entity support lives in TWO places (#334): this dict (auto-introspected →   │
# │ the validator accepts the entity) AND `_resolve_entity` (hand-maintained → the  │
# │ executor runs it). Adding an entity here WITHOUT a `_resolve_entity` branch     │
# │ makes a query validate but 400 `invalid_entity` at execution. Wire BOTH.        │
# └─────────────────────────────────────────────────────────────────────────────────┘
# OQO entity type (== oqo.get_rows / validator.VALID_ENTITIES) -> fields module.
# Hyphenated OQO types map to underscored package names.
ENTITY_FIELDS_MODULES = {
    "works": "works.fields",
    "authors": "authors.fields",
    "institutions": "institutions.fields",
    "sources": "sources.fields",
    "publishers": "publishers.fields",
    "funders": "funders.fields",
    "topics": "topics.fields",
    "keywords": "keywords.fields",
    "concepts": "concepts.fields",
    "domains": "domains.fields",
    "fields": "fields.fields",
    "subfields": "subfields.fields",
    "countries": "countries.fields",
    "continents": "continents.fields",
    "languages": "languages.fields",
    "licenses": "licenses.fields",
    "oa-statuses": "oa_statuses.fields",
    "sdgs": "sdgs.fields",
    "source-types": "source_types.fields",
    "institution-types": "institution_types.fields",
    "work-types": "work_types.fields",
    "awards": "awards.fields",
    "locations": "locations.fields",
}


def _build_entity_properties(entity_type, module_name):
    """Introspect one entity's live fields into {property_name: Property}.

    Each `Property` is also annotated (#381) with its canonical `display_name` +
    input `aliases`, resolved from `core.display_names` here — this is the layer
    that knows the owning `entity_type` (the same `param` can carry a different
    label per entity), which the entity-agnostic `Field.to_property()` cannot.
    """
    mod = importlib.import_module(module_name)
    fields_dict = getattr(mod, "fields_dict", None)
    if fields_dict is None:
        fields_dict = {f.param: f for f in getattr(mod, "fields", [])}
    out = {}
    for param, field in fields_dict.items():
        display_name, aliases = resolve_display_name(entity_type, param)
        out[param] = replace(
            field.to_property(), display_name=display_name, aliases=aliases
        )
    return out


def build_properties():
    """Build the full {entity_type: {property_name: Property}} catalog from live fields."""
    properties = {}
    for entity_type, module_name in ENTITY_FIELDS_MODULES.items():
        properties[entity_type] = _build_entity_properties(entity_type, module_name)
    return properties


# Built once at import (boot). Import is cheap — it only walks already-constructed
# Field objects; it does not touch Elasticsearch.
ENTITY_PROPERTIES = build_properties()


def get_entity_properties(entity_type):
    """Return {property_name: Property} for an entity type, or None if unknown."""
    return ENTITY_PROPERTIES.get(entity_type)


def get_property(entity_type, property_name):
    """Return the `Property` for one column, or None if entity/property unknown."""
    return ENTITY_PROPERTIES.get(entity_type, {}).get(property_name)


# ---------------------------------------------------------------------------
# Canonical render + content fingerprint (#331 Phase 2)
#
# The catalog is the runtime source of truth; the rendered payload below is its
# deterministic, fingerprintable wire form. EVERYTHING is sorted — entities,
# property names, and (via `Property.serialize()`) each property's operators and
# actions — so `json.dumps(..., sort_keys=True)` over it is byte-identical across
# fresh boots. The fingerprint is a sha256 of those canonical bytes; it is stable
# by construction and never flaps on dict/set iteration order. The committed
# `docs/properties-snapshot.json` is the pretty-printed mirror of this output and
# the CI drift baseline.
# ---------------------------------------------------------------------------


def _merged_properties(entity_type):
    """One entity's PUBLIC property set: filter-columns ∪ selectable result-fields
    (#318, Decision D), keyed by name, `actions` unioned. Returns {name: Property}.

    Two source namespaces are reconciled here:
      * filter columns — keyed by `param` (e.g. `open_access.is_oa`,
        `publication_year`), each already a `Property` in `ENTITY_PROPERTIES`
        with `actions=["filter"]` (some also `"search"`);
      * selectable fields — keyed by result-schema field name (e.g.
        `open_access`, `publication_year`, `abstract_inverted_index`), the exact
        set `?select=` validates against (`get_selectable_fields`).
    A property exists if it is filterable OR selectable. When a name is BOTH
    (e.g. `publication_year`), `"select"` is unioned into the existing actions.
    A select-only field (e.g. `open_access`, `abstract_inverted_index`) becomes a
    new `Property` with `actions=["select"]` and no filter `type`/`operators` —
    it is selectable but not filterable, and the `actions` discriminator keeps the
    two never conflated.

    This union is PUBLIC/render surface only. `ENTITY_PROPERTIES` (and therefore
    `get_entity_properties`/`get_property`) stays the filter-column projection the
    validator keys filter/sort/group_by checks off; `select` is validated against
    `get_selectable_fields`. Both the validator and this render draw from the same
    two sources, so the public catalog can't drift from what the server accepts.
    """
    merged = dict(ENTITY_PROPERTIES.get(entity_type, {}))  # name -> Property (filter)
    for name in get_selectable_fields(entity_type) or set():
        existing = merged.get(name)
        if existing is None:
            display_name, aliases = resolve_display_name(entity_type, name)
            merged[name] = Property(
                name=name, type=None, operators=[], actions=["select"],
                display_name=display_name, aliases=aliases,
            )
        elif "select" not in existing.actions:
            merged[name] = replace(existing, actions=existing.actions + ["select"])
    return merged


def _canonical_catalog():
    """The full {entity: {property_name: serialized}} catalog, fully sorted.

    Each entity's properties are the filter-columns ∪ selectable result-fields
    union (`_merged_properties`). Entities and property names sorted here;
    operators/actions sorted inside `Property.serialize()`. This is the exact
    object the fingerprint hashes."""
    return {
        entity: {
            name: merged[name].serialize() for name in sorted(merged)
        }
        for entity in sorted(ENTITY_PROPERTIES)
        for merged in (_merged_properties(entity),)
    }


def canonical_bytes(catalog):
    """The canonical UTF-8 bytes the fingerprint is taken over. Compact +
    sort_keys so the encoding is total-order deterministic, independent of how
    the dict was built."""
    return json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")


def properties_fingerprint(catalog=None):
    """sha256 hex of the canonical catalog bytes. Hashes ONLY the properties
    (not `meta`) so the fingerprint moves iff the contract content moves —
    `PROPERTIES_VERSION` is independent (human-curated)."""
    if catalog is None:
        catalog = _canonical_catalog()
    return hashlib.sha256(canonical_bytes(catalog)).hexdigest()


def render_properties(entity=None):
    """Render the canonical `/properties` payload: `{meta, properties}`.

    `meta` carries the human `version`, the content `fingerprint`, and counts —
    all describing the FULL catalog (the contract identity), even when `entity`
    slices the `properties` block to a single entity type. Callers must validate
    `entity` (404 on unknown) before slicing; an unknown entity yields `{}` here.
    """
    catalog = _canonical_catalog()
    fingerprint = properties_fingerprint(catalog)
    properties = catalog if entity is None else {entity: catalog.get(entity, {})}
    meta = {
        "version": PROPERTIES_VERSION,
        "fingerprint": fingerprint,
        "entity_count": len(catalog),
        "property_count": sum(len(props) for props in catalog.values()),
    }
    if entity is not None:
        meta["entity"] = entity
    return {"meta": meta, "properties": properties}


# ---------------------------------------------------------------------------
# Selectable result-fields (#318) — the `select` projection source.
#
# `select` fields are the entity's *result-schema* fields (what each returned
# row serializes), a DIFFERENT set from the filter-column properties above:
# e.g. `abstract` is selectable but not filterable; the filter column
# `open_access.is_oa` corresponds to the selectable parent field `open_access`.
# So we source selectable fields from each entity's MessageSchema (its `results`
# nested schema's declared fields) — the exact same set
# `core.utils.process_only_fields` validates the URL `?select=` against, so OQO
# `select` and URL `select` accept identical field sets. Lazily built + cached:
# importing every MessageSchema at boot is unnecessary work for a rarely-used
# validation path.
# ---------------------------------------------------------------------------

_SELECTABLE_CACHE = {}


def get_selectable_fields(entity_type):
    """Return the set of selectable result-field names for an entity type, or
    None if the entity is unknown / has no resolvable MessageSchema.

    `entity_type` is an OQO `get_rows` property-catalog key (e.g. "works", "work-types").
    """
    if entity_type in _SELECTABLE_CACHE:
        return _SELECTABLE_CACHE[entity_type]
    module_name = ENTITY_FIELDS_MODULES.get(entity_type)
    if module_name is None:
        return None
    # "works.fields" -> "works"; import its sibling "<pkg>.schemas.MessageSchema".
    pkg = module_name.rsplit(".", 1)[0]
    try:
        schemas_mod = importlib.import_module(f"{pkg}.schemas")
    except ImportError:
        return None
    message_schema = getattr(schemas_mod, "MessageSchema", None)
    if message_schema is None:
        return None
    results_field = message_schema._declared_fields.get("results")
    nested = getattr(results_field, "nested", None)  # the entity result Schema
    declared = getattr(nested, "_declared_fields", None)
    if declared is None:
        return None
    fields = set(declared.keys())
    _SELECTABLE_CACHE[entity_type] = fields
    return fields
