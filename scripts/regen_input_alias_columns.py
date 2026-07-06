#!/usr/bin/env python3
"""Regenerate query_translation/input_alias_columns.py from the vendored GUI
facet registry (oxjob #569).

The two allowlists in that module gate which raw column_ids the URL→OQO parser
accepts as input aliases (GUI-parity lens, Jason 2026-06-08). They used to be a
hand-frozen snapshot of `openalex-gui/src/facetConfigs.js` with NO staleness
detection — a facet added to the GUI silently didn't parse in OQL (the same
silent-drift class as the pre-#565 namespace maps). Now:

  source of truth = scripts/client_registry.json (the vendored facetConfigs.js
  extraction that the properties-gate label/subset checks already ride;
  refresh it with scripts/extract_client_registry.mjs against a local
  openalex-gui checkout) + the curated extras below.

  derivation     = a column is "GUI-faceted" on an entity iff its registry
  entry for that entity carries the `filter` action (the #450 action contract)
  AND the column exists in the live server property catalog for that entity.

  CI gate        = scripts/check_input_alias_columns.py recomputes this and
  fails when the committed snapshot differs ("run the regen script").

Run:  PYTHONPATH=. python scripts/regen_input_alias_columns.py
Deterministic + idempotent: output is fully sorted; running twice is a no-op.
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CLIENT_REGISTRY = os.path.join(_REPO_ROOT, "scripts", "client_registry.json")
TARGET = os.path.join(_REPO_ROOT, "query_translation", "input_alias_columns.py")

# client-registry entity name -> server catalog (OQO get_rows) name, where they
# differ. (The GUI says "types"; the server catalog says "work-types".)
ENTITY_ALIAS = {"types": "work-types"}

# Curated works extras (oxjob #569): works input-alias columns that are NOT
# GUI-filter-faceted today but stay accepted — the documented-API arm of the
# original allowlist ("(facetConfigs works facets) ∪ (docs filter-works.md) ∩
# works registry", Jason 2026-06-08) plus columns the GUI has since unfaceted
# (parse capability is never silently removed on works). The standing
# friendly-name audit curates these into `oql_lang._FIELDS` over time; once a
# column is curated its raw id parses via its own alias, so this list shrinks
# toward empty. Curated by hand — the generator only sorts it.
CURATED_EXTRA_WORKS_COLUMNS = frozenset({
    'abstract.search', 'apc_list.currency', 'apc_list.provenance', 'apc_list.value',
    'apc_list.value_usd', 'apc_paid.currency', 'apc_paid.provenance', 'apc_paid.value',
    'author.id', 'author.orcid', 'authorships.affiliations.institution_ids',
    'authorships.author.orcid', 'authorships.institutions.country_code',
    'authorships.institutions.id', 'authorships.institutions.is_global_south',
    'authorships.institutions.ror', 'authorships.is_corresponding',
    'best_oa_location.source.host_organization', 'best_oa_location.source.id',
    'best_oa_location.source.is_in_doaj', 'best_oa_location.source.issn',
    'best_oa_location.source.type', 'best_oa_location.version', 'best_open_version',
    'biblio.first_page', 'biblio.issue', 'biblio.last_page', 'biblio.volume',
    'cited_by', 'cites', 'concept.id', 'concepts.id', 'concepts.wikidata',
    'concepts_count', 'created_date', 'default.search', 'display_name', 'doi',
    'from_publication_date', 'fulltext_origin', 'has_content.grobid_xml',
    'has_fulltext', 'has_oa_accepted_or_published_version',
    'has_oa_submitted_version', 'has_pmcid', 'has_references', 'ids.mag',
    'ids.openalex', 'ids.pmcid', 'ids.pmid', 'institutions.continent',
    'institutions.country_code', 'institutions.id', 'institutions.ror',
    'is_corresponding', 'is_oa', 'is_paratext', 'locations.is_accepted',
    'locations.is_oa', 'locations.is_published', 'locations.license',
    'locations.source.host_institution_lineage', 'locations.source.host_organization',
    'locations.source.host_organization_lineage', 'locations.source.is_core',
    'locations.source.is_in_doaj', 'locations.source.issn',
    'locations.source.publisher_lineage', 'locations.source.type',
    'locations.version', 'locations_count', 'oa_status',
    'primary_location.is_accepted', 'primary_location.is_oa',
    'primary_location.is_published', 'primary_location.license',
    'primary_location.source.has_issn', 'primary_location.source.host_organization',
    'primary_location.source.host_organization_lineage',
    'primary_location.source.issn', 'primary_location.version', 'publication_date',
    'referenced_works', 'to_created_date', 'to_publication_date', 'to_updated_date',
    'topics.domain.id', 'topics.field.id', 'topics.id', 'topics.subfield.id',
    'type_crossref', 'updated_date',
})

# Per-entity curated extras (oxjob #569): columns the 2026-06-08 snapshot had
# (then GUI-filter-faceted) that the GUI has since UNFACETED (actions moved to
# sort/column only). Kept so OQL parse/render capability is never silently
# removed by a GUI pruning — e.g. `funders where h-index > 20` still parses,
# and `h-index` still renders friendly everywhere it exists (the
# `_faceted_everywhere` render gate needs every in-scope entity to accept the
# word). Jason: prune any of these DELIBERATELY if GUI parity should shrink.
CURATED_EXTRA_BY_ENTITY = {
    "funders": frozenset({
        "awards_count", "cited_by_count", "ids.crossref", "ids.doi", "ids.ror",
        "ids.wikidata", "summary_stats.2yr_mean_citedness",
        "summary_stats.h_index", "summary_stats.i10_index", "works_count",
    }),
    "institutions": frozenset({
        "summary_stats.2yr_mean_citedness", "summary_stats.h_index",
        "summary_stats.i10_index", "x_concepts.id",
    }),
    "publishers": frozenset({
        "country_codes", "hierarchy_level", "ids.ror", "ids.wikidata",
        "parent_publisher", "summary_stats.2yr_mean_citedness",
        "summary_stats.h_index", "summary_stats.i10_index",
    }),
    "sources": frozenset({
        "first_publication_year", "issn_l",
    }),
    # concepts entered the fallback scope in the #569 regen (the GUI filter-
    # facets works_count/cited_by_count there); its registry ALSO carries the
    # summary_stats family unfaceted, which would flip the `h-index` family's
    # render to raw EVERYWHERE via the `_faceted_everywhere` gate. Accept the
    # words on concepts too (the registry supports filtering them) so the
    # pre-#569 friendly renders stand.
    "concepts": frozenset({
        "summary_stats.2yr_mean_citedness", "summary_stats.h_index",
        "summary_stats.i10_index",
    }),
}

HEADER = '''"""Input-alias allowlists for raw registry column_ids (oxjob #363 / #569).

GENERATED FILE — do not hand-edit. Regenerate with:

    PYTHONPATH=. python scripts/regen_input_alias_columns.py

Source of truth = scripts/client_registry.json (the vendored openalex-gui
facetConfigs.js extraction; refresh via scripts/extract_client_registry.mjs)
+ the curated works extras in the regen script. A CI step
(scripts/check_input_alias_columns.py, properties-gate workflow) fails when
this snapshot drifts from a recomputation — so a GUI facet change becomes
loud here instead of silently not parsing in OQL.

OQL accepts a raw registry column_id as an INPUT alias only for columns that
are surfaced to users somewhere: the openalex-gui facet picker (`filter`
action) or the documented API (the curated extras). This deliberately
EXCLUDES registry columns that are neither — internal / half-baked /
redundant fields that would only confuse people (GUI + docs parity; nothing
more — Jason, 2026-06-08). The standing friendly-name audit curates these
into `oql_lang._FIELDS` over time; a curated column no longer needs this
fallback, so these sets shrink toward empty.
"""

'''


def derive(client_registry, entity_properties):
    def filter_cols(entity):
        entries = dict(client_registry.get(entity) or [])
        props = entity_properties.get(ENTITY_ALIAS.get(entity, entity)) or {}
        return {k for k, v in entries.items()
                if "filter" in (v.get("actions") or []) and k in props}

    works_props = entity_properties.get("works") or {}
    input_alias = filter_cols("works") | {
        c for c in CURATED_EXTRA_WORKS_COLUMNS if c in works_props}
    by_entity = {}
    for ent in client_registry:
        if ent == "works":
            continue
        server_ent = ENTITY_ALIAS.get(ent, ent)
        props = entity_properties.get(server_ent) or {}
        extras = {c for c in CURATED_EXTRA_BY_ENTITY.get(server_ent, ())
                  if c in props}
        cols = filter_cols(ent) | extras
        if cols:
            by_entity[server_ent] = cols
    return input_alias, by_entity


def render_module(input_alias, by_entity):
    def fmt_set(cols, indent):
        pad = " " * indent
        lines = []
        for c in sorted(cols):
            lines.append(f"{pad}'{c}',")
        return "\n".join(lines)

    parts = [HEADER]
    parts.append("# (GUI works filter facets) ∪ (curated extras) ∩ works registry\n")
    parts.append("INPUT_ALIAS_COLUMNS = frozenset({\n"
                 + fmt_set(input_alias, 4) + "\n})\n\n\n")
    parts.append("# Per-entity GUI-faceted columns (non-works): the entity-aware registry\n"
                 "# fallback surface (oxjob #406 increment 1b).\n")
    parts.append("GUI_FACETED_COLUMNS_BY_ENTITY = {\n")
    for ent in sorted(by_entity):
        parts.append(f"    '{ent}': frozenset({{\n"
                     + fmt_set(by_entity[ent], 8) + "\n    }),\n")
    parts.append("}\n")
    return "".join(parts)


def compute():
    from core.properties import ENTITY_PROPERTIES
    client_registry = json.load(open(CLIENT_REGISTRY))
    return derive(client_registry, ENTITY_PROPERTIES)


def main():
    input_alias, by_entity = compute()
    text = render_module(input_alias, by_entity)
    old = open(TARGET).read() if os.path.exists(TARGET) else ""
    if text == old:
        print("input_alias_columns.py unchanged")
        return
    open(TARGET, "w").write(text)
    print(f"wrote {TARGET}: {len(input_alias)} works input-alias columns, "
          f"{len(by_entity)} entities")


if __name__ == "__main__":
    main()
