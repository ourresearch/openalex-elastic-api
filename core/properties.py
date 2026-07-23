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
import os
from dataclasses import replace

from core.display_names import resolve_display_name
from core.fields import Property
from core.oxurl_documented import OXURL_DOCUMENTED_WORKS_COLUMNS
from core.property_categories import resolve_category
from core.validate import group_by_rejection

# The action/capability vocabulary (#450): which clauses may target a property.
# Defined ahead of the boot-time catalog build, which bakes the derived
# `sort`/`group_by` onto every property via `_derive_actions`.
CAP_FILTER = "filter"
CAP_SORT = "sort"
CAP_GROUP_BY = "group_by"
CAP_COLUMN = "column"

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
# 1.12.0 (#406 follow-up): capitalize the `ids.openalex` display_name "openalex id" →
# "OpenAlex ID" across all 8 entities that carry it (works + the 7 from 1.11.0), so the
# label is properly cased AND consistent with the gui facet. The 1.11.0 lowercase form
# tripped the #381 label-consistency gate (gui still showed the old singular labels);
# this reconciles BOTH sides to "OpenAlex ID" (gui facetConfigs.js + client_registry.json
# regenerated in the same ship). display_name tweak only. Jason-approved 2026-06-09. = MINOR.
# 1.13.0 (#441): added a nullable `category` to every property — a best-effort organizational
# grouping mirroring the GUI's facetConfigs categories (the 11 + one addition, "dates").
# Purely descriptive (no query-behavior effect), resolved by the builder from
# core/property_categories.py; nullable where no clear bucket (no enforcement gate). Net-new
# attribute on every property → whole snapshot re-renders, but no previously-valid query
# breaks. Jason-approved 2026-06-10. = MINOR.
# 2.0.0 (#446 identity realignment): ~20 duplicate alias spellings on works were DEMOTED from
# the top-level catalog (e.g. is_oa, institution.id/institutions.id, cites, journal,
# title.search[.exact]) — they fold into their ONE canonical property's new public
# `alternate_keys` list. The aliases stay fully accepted by the filter API / OQO validator /
# OQL parse (demoted, NOT deprecated — `fields_dict` is still 1:1), but removing them as
# top-level `/properties` entries is a MAJOR contract change (a client enumerating the catalog
# no longer sees the alias key). The new additive `alternate_keys` field rides along (MINOR on
# its own, subsumed by the MAJOR). Jason signed off the works curated merge list 2026-06-11
# (oxjobs #446); the version-class (MAJOR) was pre-approved in principle 2026-06-11 (#428 session).
# 2.1.0 (#428): added nullable `bool_true`/`bool_false` to every property — the curated boolean
# sentence phrasings ("it's open access" / "it doesn't have a DOI") that OQL renders/parses,
# single-sourced from query_translation/oql_lang.py and copied onto boolean properties at the
# catalog render layer so no-code clients (the GUI builder) can show the sentence instead of a
# raw true/false toggle. Purely descriptive (no query-behavior effect); null on non-boolean
# properties and on booleans with no curated OQL sentence. Net-new attribute on every property
# → whole snapshot re-renders, but no previously-valid query breaks. Jason-approved 2026-06-12
# (#428 session). = MINOR.
# 3.0.0 (#446 identity realignment, all-entity extension): the SAME demotion as 2.0.0, now applied
# to the other 7 entities that carried duplicate alias spellings (authors/institutions/sources/
# publishers/funders/topics/concepts) PLUS the works leftovers. Demoted to `alternate_keys`:
# OpenAlex-ID spellings (id/openalex/openalex_id → ids.openalex everywhere — aggressive, one
# identity even across the ids.openalex / ids.openalex.lower analyzer split; a bare `id` keeps its
# non-filter `select` role and stays in the catalog, only its filter role folds in), ROR/Wikidata
# short forms (ror→ids.ror, wikidata→ids.wikidata), x_concepts id spellings (concept.id/concepts.id
# → x_concepts.id), works institution short forms (institutions.continent/.is_global_south → the
# authorships.institutions.* canonicals, parallel to the already-done country_code/ror/type), works
# license_id → .license (×3 location scopes), and the works source-lineage spellings
# (host_institution_lineage + publisher_lineage → host_organization_lineage; `repository` stays a
# distinct property — own documented semantics). Same MAJOR rationale as 2.0.0 (alias keys vanish
# from the top-level catalog; still fully accepted by filter API / OQO validator / OQL parse).
# Public catalog drops: works 220→210; ~26 demotions across the other 7 entities. Jason signed off
# the curated merge decisions 2026-06-12 (oxjobs #446: aggressive ID unification; .license canonical;
# merge BOTH lineage spellings). = MAJOR.
# 4.0.0 (#450 capability surfacing): per-property `actions` is now the FULL capability
# contract {filter, search, sort, group_by, column}, derived API-actual and published —
# one registry, every consumer (OQLO charter decision 19):
#   * RENAMED the `select` action -> `column` (MAJOR; no deprecation alias — pre-launch, no
#     users). Naming map: capability = `column`, OQL keyword = `return`, WIRE unchanged
#     (`?select=` / OQO.select).
#   * ADDED `sort` to every filter-capable property. core/sort.py resolves any registry
#     field, but sorting a search column or the `collection` transport 500s in ES
#     (live-probed 2026-06-12) — capability follows the `filter` action, the set that
#     genuinely sorts.
#   * ADDED `group_by` to the filter-capable properties the live single-dim rule accepts,
#     derived from core/validate.py `group_by_rejection` — the SAME function the request
#     path enforces, so catalog and enforcement cannot drift (no dates, no search fields,
#     numerics only via GROUP_BY_RANGE_FIELD_EXCEPTIONS, minus DO_NOT_GROUP_BY /
#     referenced_works).
# The OQO validator tightened to the same sets (pre-launch; the loose membership rule had
# accepted e.g. `group by doi`, which the live API rejects). API-actual parity locked by
# tests/functional/test_capability_parity.py. Jason-approved 2026-06-12 (#450 session,
# clean-MAJOR call). = MAJOR.
# 4.1.0 (#446 thread B, friendly-name audit): curated display_name labels for ~95 filter/search
# properties that previously rendered a raw humanize() path-dump (e.g. authorships.institutions.id
# "authorships institutions id" -> "institution"; the location matrix-scope family; APC / asserted-
# institution / award / name-part families; acronym upper-casing). display_name edits only — no
# query behaviour, no operator/action/alternate_key change; clear auto-names (counts, dates, plain
# has_/is_ booleans, gui-facet labels) intentionally left as-is. No gui sync needed (none of the
# relabeled params are gui facets; #381 label-consistency gate stays green). Jason-approved
# 2026-06-12 (#446 session). = MINOR.
# 5.0.0 (#498, retire the is_xpac filter): the `is_xpac` works property is now `unlisted`
# (Field flag) — it stays LIVE/executable (legacy REST + validator + ?select=is_xpac keep
# working) but is DROPPED from the PUBLIC /properties catalog, superseded by the first-class
# `corpus` selector (#481). A top-level property REMOVAL from the contract = MAJOR. The
# OQO/OQL/oxurl boundary additionally redirects any is_xpac leaf → corpus. Jason-approved
# (clean-MAJOR call, #498 session, 2026-06-20). = MAJOR.
# 6.0.0 (#430 deprecate default.search): `default.search` was a per-entity footgun name — on works
# it duplicated `fulltext.search` (byte-identical: both route through full_search_query on the works
# index); on every non-works entity it was the ONLY handle on the broad name+alternates+description/
# keywords search (measured ≠ display_name.search — broader). Realigned via the #446 mechanism:
#   * works: `default.search`/`default.search.exact` → alternate_of `fulltext.search`/`.exact`.
#   * non-works (23 entities): minted a new HONEST canonical `text.search` (same full_search_query
#     behavior, byte-identical to the old default.search per entity) and demoted `default.search` →
#     alternate_of `text.search`. NOT named `names.search`: the broad search also covers descriptions
#     (concepts/funders/awards) and keywords (topics), so "name" would be dishonest. OQL word: `text`.
# All `default.search` spellings stay fully accepted (filter API / OQO validator / OQL parse) — demoted,
# not removed — so no live query breaks; the public catalog just drops `default.search` and gains
# `text.search`. The bare `?search=` now seeds `fulltext.search` (works) / `text.search` (non-works)
# into the OQO, fixing the #363 finding-#8 OQL render break at the source. Jason signed off option C +
# the `text.search` name 2026-06-14 (oxjobs #430). Same MAJOR rationale as 2.0.0/3.0.0/5.0.0 (a top-
# level catalog entry is removed). = MAJOR.
# 6.1.0 (#363): boolean label refresh — every boolean property's display_name was renamed to the
# short de-verbed noun the new OQL boolean surface uses (`<name> is true|false` replaced the old
# `it's …`/`it has …` special form). E.g. has_doi "has a DOI"->"has DOI", has_pmid "indexed by
# PubMed"->"PubMed", is_xpac "in extended index"->"extended index", primary_location.source.is_in_doaj
# "indexed by DOAJ"->"DOAJ", sources is_oa "fully open access"->"fully OA". Label edits only (no
# property added/removed; the always-null bool_true/bool_false fields are retained) = MINOR.
# Jason approved the rename + bump 2026-06-26 (oxjob #363).
# 6.2.0 (#557): citation-vocabulary unification — referenced_works display_name
# "references"->"cites" (the outgoing citation edge now wears the same word as the GUI
# chip and the oxurl input alias `cites:`; OQL filter leaves render as the row-subject
# verb form `it cites (…)`), with "references" demoted to an accepted input alias.
# display_name tweak + alias addition = MINOR per the versioning table. Word
# unification approved by Jason in the #557 design conversation 2026-07-04;
# MINOR class confirmed by Jason 2026-07-05.
# 7.0.0 (#565 follow-up): the 10 homonym gap columns gained `entity_type` — topics
# domain.id/field.id/subfield.id, domains fields.id, fields subfields.id, awards
# funder.id, sources host_organization, locations publisher/source_id/license. Their values
# were already name-annotated/autocompleted via #565's homonym word-resolution
# fallback; carrying the fact in the registry makes the derivation direct AND closes
# the validator gap (these columns now get the same closed-vocab / ID-shape value
# checks as their typed siblings — previously-accepted garbage values now reject).
# The classifier treats ANY entity_type transition as MAJOR ("breaks existing
# queries"); Jason chose to accept that conservative read over amending the rule
# (None->value = additive was the 1.8.0/#394 precedent). Jason-approved 2026-07-06.
# = MAJOR.
# 7.1.0: added "title/abs" as an input alias on works title_and_abstract.search
# (short form of the canonical "title/abstract"; Scopus's TITLE-ABS shorthand).
# Alias addition only, display_name unchanged. Jason-requested 2026-07-07. = MINOR.
# 7.2.0: added "name" as an input alias on display_name.search for every NON-works
# entity (a global override + the five per-entity overrides that shadow it; works
# keeps 'title' and does NOT accept "name"). Alias addition only, display_names
# unchanged. Jason-requested + approved 2026-07-17 (#611 follow-up). = MINOR.
# 7.3.0 (#396): registered CollectionField on the 12 new #394 entity endpoints
# (+12 <entity>.collection properties; part of the same-type collection: filter
# fix for path-segmented entities). Property additions = MINOR. (Entry backfilled
# by #420 — the #396 ship documented the bump only in its commit message, 97cf418.)
# 7.4.0 (#420): added `supported_by` to every property — which user-facing
# surfaces expose it ("gui" = openalex-gui filter facet, computed from the
# vendored client_registry.json; "oxurl" = documented classic REST, the curated
# works list in core/oxurl_documented.py). Replaces the retired generated
# input_alias_columns.py snapshot (+ regen/check scripts + its gate step); OQL's
# raw-column_id fallback now reads it off the registry. Purely additive key;
# the classifier treats any supported_by transition as MINOR (category-weight —
# descriptive of other surfaces, can't invalidate a /properties query). Public
# serialization + MINOR class approved by Jason 2026-07-20. = MINOR.
#
# 7.5.0 (oxjob #455 Phase B): display_name-only — "publisher" promoted from the
# alias `primary_location.source.publisher_lineage` to its canonical key
# `primary_location.source.host_organization_lineage` (identity-keyed friendly
# names; precedent = the 4.1.0 friendly-name audit). Approved by Jason
# 2026-07-21. = MINOR.
# 8.0.0 (oxjob #672): new `indexes` registry entity (crossref/pubmed/datacite/
# doaj/arxiv) + works `indexed_in` gains entity_type "indexes" (was a bare
# string filter). The entity_type transition on an existing property is what
# makes this MAJOR (the classifier treats ANY entity_type transition as MAJOR);
# the new entity catalog key itself is additive. Approved by Jason 2026-07-23.
# = MAJOR.
# 8.1.0 (oxjob #672 trailing): client_registry.json refreshed with the GUI's new
# indexes entity facets — supported_by [] -> ["gui"] on indexes.works_count and
# indexes.cited_by_count (the globally-injected range facets). Any supported_by
# transition = MINOR (category-weight). Approved by Jason 2026-07-23. = MINOR.
# 8.2.0 (oxjob #672 follow-up): works.indexed_in added to
# OXURL_DOCUMENTED_WORKS_COLUMNS — it is a documented classic REST filter, so
# its supported_by gains "oxurl" (["gui"] -> ["gui","oxurl"]). supported_by
# transition = MINOR. Approved by Jason 2026-07-23. = MINOR.
PROPERTIES_VERSION = "8.2.0"

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
    "indexes": "indexes.fields",
    "oa-statuses": "oa_statuses.fields",
    "sdgs": "sdgs.fields",
    "source-types": "source_types.fields",
    "institution-types": "institution_types.fields",
    "work-types": "work_types.fields",
    "awards": "awards.fields",
    "locations": "locations.fields",
}


# --- supported_by inputs (#420) --------------------------------------------
# The `gui` half of each property's `supported_by`: which params the openalex-gui
# facet picker filter-facets, read from the vendored client registry (the same
# committed artifact the properties-gate subset/label checks ride; refresh with
# scripts/extract_client_registry.mjs against a local GUI checkout). Computed
# here at catalog build — this replaced the generated
# query_translation/input_alias_columns.py snapshot (+ its regen/check scripts),
# so there is no frozen middle layer left to drift. Fail-loud: a missing or
# unparsable registry file is a packaging bug, not a degradable condition —
# silently returning {} would strip `gui` from every property and OQL would
# quietly stop parsing every uncurated GUI-faceted column (the silent-count-0
# failure class).
_CLIENT_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "client_registry.json",
)
# client-registry entity spelling -> catalog key, where they differ (the GUI
# says "types"; the catalog says "work-types").
_CLIENT_ENTITY_ALIAS = {"types": "work-types"}


def _load_gui_filter_columns():
    """{catalog entity_type -> frozenset of GUI filter-faceted params}."""
    with open(_CLIENT_REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    out = {}
    for client_entity, entries in registry.items():
        entity_type = _CLIENT_ENTITY_ALIAS.get(client_entity, client_entity)
        out[entity_type] = frozenset(
            param for param, cfg in (entries or {}).items()
            if "filter" in ((cfg or {}).get("actions") or [])
        )
    return out


_GUI_FILTER_COLUMNS = _load_gui_filter_columns()


def _resolve_supported_by(entity_type, param):
    """The `supported_by` surface set for one (entity, param): `gui` iff the GUI
    filter-facets it, `oxurl` iff the documented classic REST API surfaces it
    (works-only curated list). Callers only annotate params that exist in the
    live catalog, so membership is implicitly intersected with the registry
    (matching the retired regen script's `∩ catalog` rule)."""
    supported = set()
    if param in _GUI_FILTER_COLUMNS.get(entity_type, ()):
        supported.add("gui")
    if entity_type == "works" and param in OXURL_DOCUMENTED_WORKS_COLUMNS:
        supported.add("oxurl")
    return frozenset(supported)


def _build_entity_properties(entity_type, module_name):
    """Introspect one entity's live fields into {property_name: Property}.

    Each `Property` is also annotated (#381) with its canonical `display_name` +
    input `aliases`, resolved from `core.display_names` here — this is the layer
    that knows the owning `entity_type` (the same `param` can carry a different
    label per entity), which the entity-agnostic `Field.to_property()` cannot.
    The nullable `category` (#441) — a best-effort organizational grouping mirroring
    the GUI's facetConfigs categories — is resolved the same way (entity-aware,
    builder-layered, off the engine `Field`).
    """
    mod = importlib.import_module(module_name)
    fields_dict = getattr(mod, "fields_dict", None)
    if fields_dict is None:
        fields_dict = {f.param: f for f in getattr(mod, "fields", [])}
    out = {}
    for param, field in fields_dict.items():
        display_name, aliases = resolve_display_name(entity_type, param)
        category = resolve_category(entity_type, param)
        out[param] = replace(
            field.to_property(),
            actions=_derive_actions(field),
            display_name=display_name,
            aliases=aliases,
            category=category,
            supported_by=_resolve_supported_by(entity_type, param),
        )
    return _fold_alternate_keys(out, entity_type)


def _derive_actions(field):
    """One field's full action set: the Field's declared affordances
    (filter / search; [] = synthetic transport) plus the DERIVED `sort` and
    `group_by` capabilities (#450), each taken from the real engine rule so the
    catalog can't drift from what the server executes:

      * sort — every filter-capable column. API-actual: `core/sort.py` resolves
        any registry field, but a sort on a search column or the `collection`
        transport 500s in ES (live-probed 2026-06-12) — so capability follows
        the `filter` action, the set that genuinely sorts.
      * group_by — filter-capable columns the live single-dim rule accepts
        (`core.validate.group_by_rejection`: no dates, no search fields,
        numerics only via GROUP_BY_RANGE_FIELD_EXCEPTIONS, minus
        DO_NOT_GROUP_BY / referenced_works).

    The `column` capability is NOT derived here — it comes from the result
    schema (`get_selectable_fields`) and is unioned in by `_merged_properties`
    / `get_entity_capabilities`, since column-only result fields have no engine
    `Field` at all."""
    actions = list(field.actions)
    if CAP_FILTER in actions:
        actions.append(CAP_SORT)
        if group_by_rejection(field) is None:
            actions.append(CAP_GROUP_BY)
    return actions


def _fold_alternate_keys(out, entity_type):
    """Identity realignment (#446): invert each alias's `alternate_of` so the
    CANONICAL property carries the alias `param`s under `alternate_keys`.

    Aliases are LEFT IN `out` (and so in `ENTITY_PROPERTIES`) on purpose — the
    filter API, OQO validator, OQL technical-column parse, and `get_property` all
    resolve a column by membership in this dict, so demoting an alias here would
    stop it resolving (it must keep working — it's demoted, not deprecated). The
    PUBLIC `/properties` render (`_merged_properties`) is where alias entries are
    finally dropped from the top-level catalog. This pass only annotates the
    canonical side; it changes nothing about how aliases resolve.

    A misconfigured `alternate_of` (canonical `param` absent from this entity) is
    left as-is and logged — fail loud rather than silently swallow the alias.

    An alias that is ALSO `unlisted` (#593) still resolves + canonicalizes like
    any alias, but is NOT folded into the canonical's public `alternate_keys` —
    unlisted means "accept, never advertise", and that trumps the advertisement
    this fold exists to produce. Used for the never-valid authors key
    `last_known_authorships.institutions.lineage`, manufactured by a GUI
    URL-rewrite bug (2026-01 → 2026-07) and living on in users' bookmarks.
    """
    alt_map = {}  # canonical param -> [alias params]
    for param, prop in out.items():
        if prop.alternate_of and not prop.unlisted:
            alt_map.setdefault(prop.alternate_of, []).append(param)
    for canonical, alias_params in alt_map.items():
        target = out.get(canonical)
        if target is None:
            print(
                f"WARNING [properties]: {entity_type}: alternate_of points at "
                f"'{canonical}', not a property of this entity "
                f"(aliases: {sorted(alias_params)}); leaving aliases as-is."
            )
            continue
        out[canonical] = replace(
            target,
            alternate_keys=sorted(set(target.alternate_keys) | set(alias_params)),
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

# OQO entity spellings whose PROPERTY-CATALOG key differs. The one case: OQL/OQO
# say `types` (the parser + VALID_ENTITY_TYPES spelling) while the catalog is
# keyed `work-types`. Was private to the validator (`ENTITY_ALIASES`), which
# left every OTHER registry consumer entity-blind for `types` — oql_lang's
# fallback parse/render resolved no fields there at all (#611 follow-up fix,
# 2026-07-17). Now the getters below resolve it, so callers can pass either
# spelling.
ENTITY_KEY_ALIASES = {"types": "work-types"}


def resolve_entity_key(entity_type):
    """The ENTITY_PROPERTIES key for an OQO get_rows spelling (identity for all
    but the aliased spellings, e.g. "types" → "work-types"). Does NOT guarantee
    the result is a known entity — unknown strings pass through unchanged."""
    if entity_type in ENTITY_PROPERTIES:
        return entity_type
    return ENTITY_KEY_ALIASES.get(entity_type, entity_type)


def get_entity_properties(entity_type):
    """Return {property_name: Property} for an entity type, or None if unknown.
    Accepts OQO spellings ("types") as well as catalog keys ("work-types")."""
    return ENTITY_PROPERTIES.get(resolve_entity_key(entity_type))


def get_property(entity_type, property_name):
    """Return the `Property` for one column, or None if entity/property unknown."""
    return ENTITY_PROPERTIES.get(resolve_entity_key(entity_type), {}).get(property_name)


def canonicalize_column_id(column_id, entity_type):
    """Map an alias spelling of a property to its single CANONICAL column_id (#455).

    A property has one identity but many spellings (`is_oa` == `open_access.is_oa`;
    `institution.id` == `authorships.institutions.id`; `cites` == `referenced_works`;
    `journal` == `primary_location.source.id`). #446 made the catalog identity-aware by
    storing each alias's canonical under `Property.alternate_of`; this helper reads that
    datum so every query-translation surface can collapse a spelling to the one identity
    at the boundary, leaving downstream consumers (validator, canonicalizer, render, ES
    translation) canonical-only.

    Aliases stay accepted on INPUT (demoted, not deprecated) — this only rewrites them
    to canonical, never rejects. Returns `column_id` unchanged when:
      * it is already canonical (no `alternate_of`), or
      * the entity/property is unknown (let the validator surface `invalid_column`).
    Pure (reads the already-built ENTITY_PROPERTIES); safe to call per-clause.
    """
    if not column_id:
        return column_id
    prop = ENTITY_PROPERTIES.get(resolve_entity_key(entity_type), {}).get(column_id)
    if prop is not None and prop.alternate_of:
        return prop.alternate_of
    return column_id


# ---------------------------------------------------------------------------
# Unified per-property capabilities (#450)
#
# ONE catalog answering "which clauses may target property X on entity Y?" across
# all four affordances: filter / sort / group_by / column. Before #450 these were
# gated against THREE different sources — filter via ENTITY_PROPERTIES, sort and
# group_by as loose membership rules coded in the validator, and `column`/`select`
# against a SEPARATE namespace (the marshmallow MessageSchema result-schema,
# `get_selectable_fields`). Now `sort`/`group_by` are BAKED onto each Property at
# boot (`_derive_actions`, from the real engine rules) and `column` is unioned in
# from the result schema — the validator, OQL, and the public /properties contract
# all gate off the SAME per-property action set. API-actual parity is locked by
# tests/functional/test_capability_parity.py.
# Column-only result fields (open_access, authorships, id, …) are column-capable but
# carry NO filter/sort/group_by — they are not ENTITY_PROPERTIES columns. Conversely
# filter-only predicates (has_doi, *.search) can be sortable/groupable but not
# column-capable (not returnable result fields).
# ---------------------------------------------------------------------------


# Boot-static per-entity caches (ENTITY_PROPERTIES is immutable after boot):
# get_entity_capabilities runs on every OQO validation.
_CAPABILITIES_CACHE = {}


def get_entity_capabilities(entity_type):
    """{property_name: frozenset(capabilities)} for an entity, or None if the entity
    is unknown (no filter registry AND no result schema). The single source of truth
    the OQO validator gates filter/sort/group_by/column on (#450). Reads each
    Property's baked actions (`_derive_actions`) — including alias columns (#446),
    which keep the same capabilities as their canonical so a raw-URL-accepted alias
    sort/group key never rejects — and unions the `column` capability from the
    result schema."""
    entity_type = resolve_entity_key(entity_type)
    if entity_type in _CAPABILITIES_CACHE:
        return _CAPABILITIES_CACHE[entity_type]
    base = ENTITY_PROPERTIES.get(entity_type)
    selectable = get_selectable_fields(entity_type)
    if base is None and selectable is None:
        result = None
    else:
        caps = {name: set(prop.actions) for name, prop in (base or {}).items()}
        for name in (selectable or set()):
            caps.setdefault(name, set()).add(CAP_COLUMN)
        result = {name: frozenset(affordances) for name, affordances in caps.items()}
    _CAPABILITIES_CACHE[entity_type] = result
    return result


def get_entity_columns(entity_type):
    """The column-capable (returnable / `?select=`-able) property names for an entity
    — what an OQL `return` clause may name. `None` when the column set can't be
    determined (no result schema), so callers skip column validation rather than
    reject everything — preserving the pre-#450 `get_selectable_fields is None` skip."""
    selectable = get_selectable_fields(entity_type)
    return None if selectable is None else set(selectable)


def get_entity_column_catalog(entity_type):
    """{column_name: Property} for the entity's column-capable properties, with
    the display_name/aliases the public catalog carries — the friendly-name
    source the OQL `return` clause resolves and renders against (#450). Empty
    dict when the column set can't be determined."""
    columns = get_entity_columns(entity_type)
    if not columns:
        return {}
    merged = _merged_properties(entity_type)
    return {name: merged[name] for name in columns if name in merged}


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
        carrying its baked actions (filter/search + derived sort/group_by, #450);
      * selectable fields — keyed by result-schema field name (e.g.
        `open_access`, `publication_year`, `abstract_inverted_index`), the exact
        set `?select=` validates against (`get_selectable_fields`).
    A property exists if it is filterable OR selectable. When a name is BOTH
    (e.g. `publication_year`), `"column"` is unioned into the existing actions.
    A column-only field (e.g. `open_access`, `abstract_inverted_index`) becomes a
    new `Property` with `actions=["column"]` and no filter `type`/`operators` —
    it is returnable but not filterable, and the `actions` discriminator keeps the
    two never conflated. (The action was published as `"select"` until v3.0.0 —
    renamed to `column` to match the capability vocabulary; the WIRE param stays
    `?select=`.)

    The validator's capability catalog (`get_entity_capabilities`) performs this
    same union, so the public catalog and what the server accepts can't drift.
    """
    # Identity realignment (#446): drop alias columns (`alternate_of` set) from the
    # PUBLIC catalog — they survive only as `alternate_keys` on their canonical
    # property. They REMAIN in `ENTITY_PROPERTIES` (so filter/validator/OQL parse
    # keep resolving them); the demotion is render-surface only.
    # Also drop `unlisted` columns (#498): soft-deprecated fields that stay live
    # and resolvable in ENTITY_PROPERTIES (filter/validator/OQL parse keep working)
    # but are retired from the PUBLIC catalog because a different mechanism now
    # covers them (e.g. `is_xpac` → the `corpus` selector). See Property.unlisted.
    all_props = ENTITY_PROPERTIES.get(entity_type, {})
    merged = {
        name: prop
        for name, prop in all_props.items()
        if not prop.alternate_of and not prop.unlisted
    }
    # An `unlisted` column that is ALSO a selectable result field (e.g. `is_xpac`,
    # which is in WorksSchema) must not sneak back in via the column union below —
    # otherwise it'd reappear as a `column`-only property. Drop it there too so the
    # retirement is total in the public catalog. (It stays serialized in entity
    # output + `?select=is_xpac` still resolves — unlisted is a catalog hide, not a
    # functional removal.)
    _unlisted = {name for name, prop in all_props.items() if prop.unlisted}
    for name in get_selectable_fields(entity_type) or set():
        if name in _unlisted:
            continue
        existing = merged.get(name)
        if existing is None:
            display_name, aliases = resolve_display_name(entity_type, name)
            merged[name] = Property(
                name=name, type=None, operators=[], actions=[CAP_COLUMN],
                display_name=display_name, aliases=aliases,
                category=resolve_category(entity_type, name),
            )
        elif CAP_COLUMN not in existing.actions:
            merged[name] = replace(existing, actions=existing.actions + [CAP_COLUMN])
    # Boolean sentence phrasings (#428) were REMOVED in #363: booleans are now plain
    # `<name> is true|false` clauses, so there is no `bool_true`/`bool_false` sentence
    # to copy. The nullable Property fields remain (always None) to keep the
    # /properties schema stable — dropping them is a MAJOR change for a later pass.
    return merged


# Built once per process (the catalog is boot-static); /properties serves it on
# every request. Treat the cached object as immutable.
_CANONICAL_CATALOG_CACHE = None


def _canonical_catalog():
    """The full {entity: {property_name: serialized}} catalog, fully sorted.

    Each entity's properties are the filter-columns ∪ selectable result-fields
    union (`_merged_properties`). Entities and property names sorted here;
    operators/actions sorted inside `Property.serialize()`. This is the exact
    object the fingerprint hashes."""
    global _CANONICAL_CATALOG_CACHE
    if _CANONICAL_CATALOG_CACHE is None:
        _CANONICAL_CATALOG_CACHE = {
            entity: {
                name: merged[name].serialize() for name in sorted(merged)
            }
            for entity in sorted(ENTITY_PROPERTIES)
            for merged in (_merged_properties(entity),)
        }
    return _CANONICAL_CATALOG_CACHE


def canonical_bytes(catalog):
    """The canonical UTF-8 bytes the fingerprint is taken over. Compact +
    sort_keys so the encoding is total-order deterministic, independent of how
    the dict was built."""
    return json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")


_FINGERPRINT_CACHE = None


def properties_fingerprint(catalog=None):
    """sha256 hex of the canonical catalog bytes. Hashes ONLY the properties
    (not `meta`) so the fingerprint moves iff the contract content moves —
    `PROPERTIES_VERSION` is independent (human-curated). The default (whole
    canonical catalog) is boot-static, so its hash is computed once."""
    global _FINGERPRINT_CACHE
    if catalog is None or catalog is _CANONICAL_CATALOG_CACHE:
        if _FINGERPRINT_CACHE is None:
            _FINGERPRINT_CACHE = hashlib.sha256(
                canonical_bytes(_canonical_catalog())).hexdigest()
        return _FINGERPRINT_CACHE
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
    entity_type = resolve_entity_key(entity_type)
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
