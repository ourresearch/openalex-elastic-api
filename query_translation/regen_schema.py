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
        "$id": "https://openalex.org/schemas/oqo/v1.3",
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
            "round-trip to identical JSON (quote every string value on emit)."
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
                    "Group-by dimensions (Stage B). A LIST, so multi-dimensional "
                    "grouping (e.g. topic x year) is expressible; dimension order "
                    "is meaningful. Live serving impl is single-dimension only "
                    "(multi-dim deferred to #297)."
                ),
                "items": {"$ref": "#/$defs/GroupBy"},
                "default": [],
            },
            "sort_by": {
                "type": "array",
                "description": (
                    "Sort keys, applied in order as primary/secondary/… "
                    "tiebreakers. A LIST, so a multi-column sort "
                    "(`sort=publication_year:desc,cited_by_count:desc`) is "
                    "expressible; list order is meaningful and is preserved (NOT "
                    "sorted). Absent/empty ⇒ the entity's implicit default sort."
                ),
                "items": {"$ref": "#/$defs/SortBy"},
                "default": [],
            },
            "sample": {
                "type": ["integer", "null"],
                "minimum": 1,
                "maximum": 10000,
                "description": "Return a random sample of N results instead of all matches.",
                "default": None,
            },
            "select": {
                "type": "array",
                "description": (
                    "Column projection (#318): the columns each returned row "
                    "should carry, e.g. ['id','display_name','cited_by_count']. "
                    "Order is meaningful (display order). Absent/empty ⇒ the "
                    "full object. Valid values are the entity's column-capable "
                    "properties (the registry `column` capability, #450 — the "
                    "same set the URL `?select=` accepts), NOT its filter "
                    "predicates. OQL surface: the `return col1, col2` clause."
                ),
                "items": {"type": "string"},
                "default": [],
            },
            "seed": {
                "type": ["string", "integer", "null"],
                "description": (
                    "Seed that makes a `sample` reproducible. Only meaningful "
                    "alongside `sample`; ignored (with a warning) otherwise."
                ),
                "default": None,
            },
            "per_page": {
                "type": ["integer", "null"],
                "minimum": 1,
                "maximum": 200,
                "description": (
                    "Page size (#318). Default 25, max 200 — applied at "
                    "execution, so a canonical OQO leaves it absent when unset."
                ),
                "default": None,
            },
            "page": {
                "type": ["integer", "null"],
                "minimum": 1,
                "description": (
                    "Offset page number (1-based). Mutually exclusive with "
                    "`cursor`; absent both ⇒ page 1."
                ),
                "default": None,
            },
            "cursor": {
                "type": ["string", "null"],
                "description": (
                    "Cursor-pagination token ('*' to start; opaque thereafter). "
                    "Mutually exclusive with `page`."
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
                "description": "A single group-by dimension.",
                "required": ["column_id"],
                "additionalProperties": False,
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "The column to group by.",
                        "examples": ["primary_topic.id", "publication_year", "authorships.countries", "sustainable_development_goals.id"],
                    },
                },
            },
            "SortBy": {
                "type": "object",
                "description": (
                    "A single sort key: a column plus a direction. `column_id` "
                    "may be a real sortable column or a synthetic sort key — "
                    "'relevance_score' (requires a search clause; descending "
                    "only) or, when a group_by is present, the bucket-ordering "
                    "keys 'count' / 'key'. With a group_by, `aggregate` "
                    "(mean/sum/min/max) orders the buckets by a metric "
                    "sub-aggregation of a numeric `column_id` — e.g. funders "
                    "ranked by mean(cited_by_count); URL form "
                    "'cited_by_count.mean:desc'."
                ),
                "required": ["column_id"],
                "additionalProperties": False,
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "The column/field to sort by.",
                        "examples": ["cited_by_count", "publication_year", "fwci", "display_name", "works_count", "relevance_score"],
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Sort direction. 'asc' ascending, 'desc' descending. Defaults to 'asc'.",
                        "default": "asc",
                    },
                    "aggregate": {
                        "type": "string",
                        "enum": ["mean", "sum", "min", "max"],
                        "description": (
                            "Metric sub-aggregation to order group_by buckets by "
                            "(only valid with a group_by, over a numeric "
                            "column_id). URL form: '<column_id>.<aggregate>:<direction>', "
                            "e.g. 'cited_by_count.mean:desc'."
                        ),
                    },
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
                "description": "Sort + sample (top-cited sample)",
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "publication_year", "value": 2024, "operator": ">="}],
                          "sort_by": [{"column_id": "cited_by_count", "direction": "desc"}], "sample": 100},
            },
            {
                "description": "Multi-column sort: newest first, then most-cited as a tiebreaker",
                "value": {"get_rows": "works",
                          "sort_by": [
                              {"column_id": "publication_year", "direction": "desc"},
                              {"column_id": "cited_by_count", "direction": "desc"},
                          ]},
            },
            {
                "description": "Logistics layer (#318): projection + reproducible sample + pagination, all self-contained",
                "value": {"get_rows": "works",
                          "filter_rows": [{"column_id": "publication_year", "value": 2024, "operator": ">="}],
                          "select": ["id", "display_name", "cited_by_count"],
                          "sample": 50, "seed": "42",
                          "per_page": 25, "page": 2},
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
