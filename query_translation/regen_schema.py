#!/usr/bin/env python3
"""Regenerate docs/oqo-schema.json (JSON Schema) from the canonical OQO dataclass.

The schema's *structure* mirrors `query_translation/oqo.py`; the dynamic parts —
the entity-type enum and the operator enum — are pulled live from the module
constants (`VALID_ENTITY_TYPES`, `VALID_OPERATORS`), so the schema can never drift
from the dataclass's source of truth. Output is deterministic: re-running produces
a byte-identical file (#284 ACCEPTANCE Test 1).

Usage:
    python -m query_translation.regen_schema           # writes docs/oqo-schema.json
    python -m query_translation.regen_schema --check    # exit 1 if out of date
"""
import json
import os
import sys

# import the dataclass module directly to avoid the package __init__ (web deps)
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
SCHEMA_PATH = os.path.join(_REPO, "docs", "oqo-schema.json")


def _load_oqo_module():
    spec = importlib.util.spec_from_file_location("_oqo_src", os.path.join(_HERE, "oqo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_schema() -> dict:
    oqo = _load_oqo_module()
    entity_types = sorted(oqo.VALID_ENTITY_TYPES)
    operators = sorted(oqo.VALID_OPERATORS)  # {<, <=, >, >=, has, is}
    corpora = sorted(oqo.VALID_CORPORA)  # {all, core, expansion}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://openalex.org/schemas/oqo/v1.5",
        "name": "OpenAlex_Query_Object",
        "description": (
            "The canonical JSON representation for OpenAlex queries. OQO is the "
            "intermediate format for bidirectional translation between URL "
            "parameters, OQL (human-readable query language), and programmatic "
            "JSON access. GENERATED from query_translation/oqo.py by "
            "query_translation/regen_schema.py — do not hand-edit. Entity values "
            "are BARE (the namespace is the column_id, resolved via the column "
            "registry): 'I136199984', 'de', 'article', '13' — never "
            "'institutions/I136199984'. Negation is the per-node 'is_negated' "
            "polarity bit; the canonical form is NNF (negation on leaves only). "
            "JSON is the normative serialization; YAML is display-only and MUST "
            "round-trip to identical JSON (quote every string value on emit). "
            "The OQO describes WHICH ROWS a query matches — nothing else (#661 "
            "query/view split, v1.4). View/presentation parameters (sort, column "
            "projection, pagination) are NOT part of the OQO; they travel as "
            "sibling request parameters on the execute surface, in the classic "
            "URL syntax: `sort=<col>[:asc|desc][,…]`, `select=<col>,[…]`, "
            "`page`, `per_page`, `cursor` — as query-string params on "
            "`GET /?oqo=…` / `GET /?oql=…`, or as sibling top-level body keys "
            "on `POST / {\"oqo\": …, \"sort\": …}`."
        ),
        "type": "object",
        "required": ["get_rows"],
        "additionalProperties": False,
        "properties": {
            "get_rows": {
                "$ref": "#/$defs/EntityType",
                "description": "The entity type to retrieve (works, authors, institutions, ...).",
            },
            "corpus": {
                "type": "string",
                "enum": corpora,
                "default": "core",
                "description": (
                    "Which corpus(es) seed the base result set (works only): "
                    "'core' (the curated corpus, default), 'expansion' (the "
                    "expansion corpus alone — broader coverage, lower quality), or "
                    "'all' (core + expansion). A corpus SELECTION, distinct from a "
                    "filter (which only narrows an already-chosen corpus). Absent "
                    "⇒ 'core'."
                ),
            },
            "filter_rows": {
                "type": "array",
                "description": "Filters applied to the retrieved rows. Top-level items are implicitly AND-joined.",
                "items": {"$ref": "#/$defs/Filter"},
                "default": [],
            },
            "group_by": {
                "type": "array",
                "description": (
                    "The splits, outermost first (up to three): OQL's `group those "
                    "works by ...` steps (oxjob #1530). Order is meaningful. A split "
                    "is a column, or listed values / searches of a column, or bins of "
                    "a number column, or a list of conditions; any split may filter "
                    "its groups (`where`)."
                ),
                "items": {"$ref": "#/$defs/GroupBy"},
                "maxItems": 3,
                "default": [],
            },
            "calculate": {
                "type": "array",
                "description": (
                    "OQL's final `summarize using ...` step (oxjob #1530, #1555): the measures "
                    "computed for each group and for the total row (the whole "
                    "starting set), or for the whole set when there is no split."
                ),
                "items": {"$ref": "#/$defs/Measure"},
                "default": [],
            },
            "sample": {
                "type": ["integer", "null"],
                "minimum": 1,
                "maximum": 10000,
                "description": "Return a random sample of N results instead of all matches.",
                "default": None,
            },
            "seed": {
                "type": ["string", "integer", "null"],
                "description": (
                    "Seed that makes a `sample` reproducible. Only meaningful "
                    "alongside `sample`; ignored (with a warning) otherwise."
                ),
                "default": None,
            },
        },
        "$defs": {
            "EntityType": {
                "type": "string",
                "description": "Valid OpenAlex entity types (the OQO `get_rows`). Sourced from oqo.VALID_ENTITY_TYPES.",
                "enum": entity_types,
            },
            "Filter": {
                "description": "A leaf filter (single condition) or a branch filter (boolean combination).",
                "oneOf": [
                    {"$ref": "#/$defs/LeafFilter"},
                    {"$ref": "#/$defs/BranchFilter"},
                ],
            },
            "LeafFilter": {
                "type": "object",
                "description": "A single filter condition (a literal = atom + polarity).",
                "required": ["column_id", "value"],
                "additionalProperties": False,
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "Filter field identifier; dot notation for nested fields. Valid columns/types come from the column registry, not this schema.",
                        "examples": [
                            "publication_year", "type", "open_access.is_oa",
                            "authorships.institutions.lineage", "title_and_abstract.search",
                            "sustainable_development_goals.id",
                        ],
                    },
                    "value": {
                        "description": "BARE value (no entity prefix). Native IDs self-namespace via their letter prefix (A/W/I/S/F/T/...); non-native values are bare slugs/codes/ints disambiguated by column_id. String for ids/slugs/search, integer for counts/years, boolean for flags, null for missing.",
                        # anyOf (not oneOf) because `integer` is a subset of
                        # `number` — an int value matches both and `oneOf`
                        # demands exactly one match.
                        "anyOf": [
                            {"type": "string"},
                            {"type": "integer"},
                            {"type": "number"},
                            {"type": "boolean"},
                            {"type": "null"},
                        ],
                        "examples": ["article", "I136199984", "de", "13", 2024, True, None],
                    },
                    "operator": {
                        "$ref": "#/$defs/Operator",
                        "description": "Comparison operator. Defaults to 'is'. Strictly affirmative — negation is `is_negated`, never an operator.",
                        "default": "is",
                    },
                    "is_negated": {
                        "type": "boolean",
                        "description": "Polarity bit. true = the negation of this leaf (the single negation mechanism; maps 1:1 to URL `!`). In canonical (NNF) form, negation lives only on leaves.",
                        "default": False,
                    },
                },
            },
            "BranchFilter": {
                "type": "object",
                "description": "A boolean combination of filters (AND/OR), optionally negated.",
                "required": ["join", "filters"],
                "additionalProperties": False,
                "properties": {
                    "join": {
                        "type": "string",
                        "enum": ["and", "or"],
                        "description": "'and' requires all children; 'or' requires at least one.",
                    },
                    "filters": {
                        "type": "array",
                        "description": "Child filters (leaf or branch), enabling nested boolean logic.",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/Filter"},
                    },
                    "is_negated": {
                        "type": "boolean",
                        "description": "Negate the whole branch. The canonicalizer pushes this to the leaves via De Morgan (NNF), so a canonical OQO has is_negated only on leaves.",
                        "default": False,
                    },
                },
            },
            "GroupBy": {
                "type": "object",
                "description": (
                    "One split. A column alone is today's group-by; at most one of "
                    "`values`, `bins`, `conditions` refines it; `where` filters the "
                    "groups. A split into conditions has no column_id."
                ),
                "additionalProperties": False,
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "The column to split by (absent for a split into conditions).",
                        "examples": ["primary_topic.id", "publication_year", "authorships.countries", "sustainable_development_goals.id"],
                    },
                    "values": {
                        "type": "array",
                        "maxItems": 100,
                        "description": (
                            "Split by these values only, one group each, in this order "
                            "(`by institution in (I1, I2)`): bare values of the column, "
                            "or one collection id; for a search column "
                            "(`title_and_abstract.search`), one filter tree per search."
                        ),
                        "items": {"anyOf": [{"type": "string"}, {"type": "integer"},
                                            {"$ref": "#/$defs/Filter"}]},
                    },
                    "bins": {
                        "type": "object",
                        "description": "Bins of a number column: `{\"at\": [edges]}` or `{\"of\": width}`.",
                        "properties": {
                            "at": {"type": "array", "items": {"type": "number"}, "maxItems": 100},
                            "of": {"type": "number", "exclusiveMinimum": 0},
                        },
                        "additionalProperties": False,
                    },
                    "conditions": {
                        "type": "array",
                        "maxItems": 100,
                        "description": "One group per condition (`into ((...), (...))`), in this order.",
                        "items": {"$ref": "#/$defs/Filter"},
                    },
                    "where": {
                        "$ref": "#/$defs/GroupFilter",
                        "description": (
                            "The group filter: measure conditions on each group's works "
                            "(`count of those works > (10)`) and the group's own fields "
                            "(a leaf in the group entity's columns: `summary_stats.h_index`, "
                            "`ids.openalex`, `collection`; the relations `co_author` on "
                            "author groups and `collaborator` on institution groups)."
                        ),
                    },
                },
            },
            "GroupFilter": {
                "description": "A group filter node: a measure condition, a leaf, or a branch of them.",
                "oneOf": [
                    {"$ref": "#/$defs/MeasureFilter"},
                    {"$ref": "#/$defs/LeafFilter"},
                    {"type": "object", "required": ["join", "filters"], "additionalProperties": False,
                     "properties": {
                         "join": {"type": "string", "enum": ["and", "or"]},
                         "filters": {"type": "array", "minItems": 1,
                                     "items": {"$ref": "#/$defs/GroupFilter"}},
                         "is_negated": {"type": "boolean", "default": False}}},
                ],
            },
            "MeasureFilter": {
                "type": "object",
                "description": "A condition on a measure of each group's works: `count of those works > (10)`.",
                "required": ["measure", "value"],
                "additionalProperties": False,
                "properties": {
                    "measure": {"type": "string", "enum": ["count", "mean", "median", "sum", "min", "max", "percent"]},
                    "column_id": {"type": "string", "description": "The measured column (absent for count)."},
                    "operator": {"type": "string", "enum": ["is", ">", ">=", "<", "<="], "default": ">"},
                    "value": {"type": "number"},
                    "is_negated": {"type": "boolean", "default": False},
                },
            },
            "Measure": {
                "type": "object",
                "description": (
                    "One calculation: `count`; `mean`/`median`/`sum`/`min`/`max` of a "
                    "number column (min/max also of a date); `percent` of a yes/no "
                    "column; `percent_of_those` (each group's share of the set it came "
                    "from); `value` (a split's own field shown beside each group, e.g. "
                    "an author's `summary_stats.h_index`)."
                ),
                "required": ["measure"],
                "additionalProperties": False,
                "properties": {
                    "measure": {"type": "string", "enum": ["count", "mean", "median", "sum", "min", "max",
                                                           "percent", "percent_of_those", "value"]},
                    "column_id": {"type": "string"},
                },
            },
            "Operator": {
                "type": "string",
                "description": "Leaf comparison operators (strictly affirmative). Sourced from oqo.VALID_OPERATORS. Negation is the `is_negated` bit, not an operator.",
                "enum": operators,
                "default": "is",
            },
        },
        "examples": [
            {
                "description": "Type filter (bare value)",
                "value": {"get_rows": "works", "filter_rows": [{"column_id": "type", "value": "article"}]},
            },
            {
                "description": "AND of filters (implicit at top level), with range + boolean flag",
                "value": {"get_rows": "works", "filter_rows": [
                    {"column_id": "type", "value": "article"},
                    {"column_id": "publication_year", "value": 2024, "operator": ">="},
                    {"column_id": "open_access.is_oa", "value": True},
                ]},
            },
            {
                "description": "OR within a field (article OR review)",
                "value": {"get_rows": "works", "filter_rows": [
                    {"join": "or", "filters": [
                        {"column_id": "type", "value": "article"},
                        {"column_id": "type", "value": "review"},
                    ]},
                ]},
            },
            {
                "description": "Negation via is_negated (COVID NOT pediatric)",
                "value": {"get_rows": "works", "filter_rows": [
                    {"column_id": "title_and_abstract.search", "value": "covid", "operator": "has"},
                    {"column_id": "title_and_abstract.search", "value": "pediatric", "operator": "has", "is_negated": True},
                ]},
            },
            {
                "description": "Stage B: multi-dimensional group_by (topic x year)",
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "publication_year", "value": 1976, "operator": ">="}],
                          "group_by": [{"column_id": "primary_topic.id"}, {"column_id": "publication_year"}]},
            },
            {
                "description": (
                    "Calculations by listed values (oxjob #1530): get works where topic is "
                    "(T10878); then group those works by institution in (I63966007, "
                    "I97018004); then, summarize using count, mean FWCI, percent open access"),
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "primary_topic.id", "value": "T10878"}],
                          "group_by": [{"column_id": "authorships.institutions.lineage",
                                        "values": ["I63966007", "I97018004"]}],
                          "calculate": [{"measure": "count"}, {"measure": "mean", "column_id": "fwci"},
                                        {"measure": "percent", "column_id": "open_access.is_oa"}]},
            },
            {
                "description": (
                    "A group filter (oxjob #1530): ... then group those works by author "
                    "where count of those works > (10) and h-index > (20)"),
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "title_and_abstract.search", "value": "kelp", "operator": "has"}],
                          "group_by": [{"column_id": "authorships.author.id", "where": {"join": "and", "filters": [
                              {"measure": "count", "operator": ">", "value": 10},
                              {"column_id": "summary_stats.h_index", "operator": ">", "value": 20}]}}]},
            },
            {
                "description": "Reproducible random sample (seed makes the sample stable)",
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "publication_year", "value": 2024, "operator": ">="}],
                          "sample": 100, "seed": "42"},
            },
        ],
    }


def render(schema: dict) -> str:
    # deterministic: fixed insertion order + 2-space indent + trailing newline
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main(argv):
    text = render(build_schema())
    if "--check" in argv:
        current = open(SCHEMA_PATH, encoding="utf-8").read() if os.path.exists(SCHEMA_PATH) else ""
        if current != text:
            print("OUT OF DATE: docs/oqo-schema.json differs from generated. Run regen_schema.", file=sys.stderr)
            return 1
        print("docs/oqo-schema.json is up to date.")
        return 0
    with open(SCHEMA_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"Wrote {SCHEMA_PATH} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
