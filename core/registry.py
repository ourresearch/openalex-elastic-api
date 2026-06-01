"""Column registry (#294 Phase B) — build-at-boot, in-memory.

A per-entity map of every queryable column, derived from the SAME live `Field`
objects the filter layer executes (each entity's `fields_dict`). Built once at
import by calling `Field.to_registry_entry()` on every field, so the registry
and the executor can never disagree — there's no committed snapshot to go stale.

    REGISTRY[entity_type][column_id] = {
        "param", "field_type", "operators", "actions",
        "alias", "custom_es_field", "entity_type",
    }

`entity_type` keys are the OQO `get_rows` strings (hyphenated where the OQO uses
hyphens, e.g. "work-types") so a caller can look up `REGISTRY[oqo.get_rows]`
directly. `column_id` keys are each field's `param` — the same space the OQO's
`LeafFilter.column_id` and `core.utils.get_field` resolve against.

Consumers: the OQO validator (`query_translation/validator.py`) and the
`GET /registry` endpoint. The offline audit tool
(`oxjobs/working/column-registry-sync/work/extract_server.py`) builds the same
shape statically via AST and is kept in sync as a cross-check, but this module —
introspecting the live objects — is the runtime source of truth.
"""

import importlib

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
    "sdgs": "sdgs.fields",
    "source-types": "source_types.fields",
    "institution-types": "institution_types.fields",
    "work-types": "work_types.fields",
    "awards": "awards.fields",
    "locations": "locations.fields",
}


def _build_entity_registry(module_name):
    """Introspect one entity's live fields into {column_id: registry_entry}."""
    mod = importlib.import_module(module_name)
    fields_dict = getattr(mod, "fields_dict", None)
    if fields_dict is None:
        fields_dict = {f.param: f for f in getattr(mod, "fields", [])}
    return {param: field.to_registry_entry() for param, field in fields_dict.items()}


def build_registry():
    """Build the full {entity_type: {column_id: entry}} registry from live fields."""
    registry = {}
    for entity_type, module_name in ENTITY_FIELDS_MODULES.items():
        registry[entity_type] = _build_entity_registry(module_name)
    return registry


# Built once at import (boot). Import is cheap — it only walks already-constructed
# Field objects; it does not touch Elasticsearch.
REGISTRY = build_registry()


def get_entity_columns(entity_type):
    """Return {column_id: entry} for an entity type, or None if unknown."""
    return REGISTRY.get(entity_type)


def get_column(entity_type, column_id):
    """Return the registry entry for one column, or None if entity/column unknown."""
    return REGISTRY.get(entity_type, {}).get(column_id)


# ---------------------------------------------------------------------------
# Selectable result-fields (#318) — the `select` projection source.
#
# `select` fields are the entity's *result-schema* fields (what each returned
# row serializes), a DIFFERENT set from the filter-column registry above:
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

    `entity_type` is an OQO `get_rows` registry key (e.g. "works", "work-types").
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
