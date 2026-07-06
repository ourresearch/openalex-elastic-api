"""Editor-support routes for the IDE-style OQL editor (oxjob #357).

Two pure endpoints (neither touches Elasticsearch directly) that back the dev
playground's CodeMirror editor:

  GET /parse-context?q=<oql>&pos=<int>   cursor -> what grammar element is expected
                                         here, for autocomplete. Always 200.
  GET /validate?q=<oql>                  full OQL -> diagnostics + canonical formats,
                                         for inline linting. Always 200.

Kept in a **separate blueprint** (not `query_translation/views.py`) so it doesn't
collide with the in-flight execution/translation reorg in that file (#384). It reuses
the pure OQL engine + the existing validator; `render_all_formats` is imported lazily
to avoid import-time coupling to `views.py`.
"""
from flask import Blueprint, jsonify, request

from query_translation.diagnostics import (
    parse_diagnostic, validation_diagnostic, OQLError as _OQLError,
)
from query_translation.oql_context import parse_context as _parse_context
from query_translation.oql_lang import (
    parse as _engine_parse, parse_collecting as _engine_parse_collecting,
    entity_type_for_column,
)
from query_translation.oql_renderer import config_vocab_items
from query_translation.validator import validate_oqo, CLOSED_VOCAB_NAMESPACE

blueprint = Blueprint("oql_editor", __name__)

# Closed-vocab value autocomplete (#357): a column's dropdown namespace derives
# from the registry — `entity_type_for_column` composed with the validator's
# CLOSED_VOCAB_NAMESPACE (oxjob #565; formerly a 6-entry hand map here that
# silently missed every closed-vocab column outside it). Only entity_types with
# a `config/*.yaml` values list produce suggestions; source-type /
# institution-type / licenses have no closed config vocab yet, so they keep the
# bare "unknown" suggestion. Covers id-kind closed vocabs too (SDGs,
# continents, domains/fields/subfields) — their /autocomplete route 404s, so
# the static vocab IS the dropdown; open id namespaces (institutions, authors)
# have no config table and contribute nothing here (the live route serves them).


def _enum_slugs(column, entity=None):
    """The closed-vocab slug suggestions for an OQL field column, or [] if the column
    has no `config/*.yaml` values list. Each entry carries a display-name `detail`
    only when it adds information beyond the slug (countries/languages), so the editor
    can match by name and insert the code."""
    namespace = CLOSED_VOCAB_NAMESPACE.get(entity_type_for_column(column, entity))
    if not namespace:
        return []
    return [
        {"value": sid, "kind": "enum-slug",
         **({"detail": name} if name.lower() != sid.lower() else {})}
        for sid, name in config_vocab_items(namespace)
    ]


def _enrich_enum_suggestions(result):
    """Attach closed-vocab value slugs in two places (mutates + returns `result`; pure,
    safe on every /parse-context response):

    1. **Value slot** — `type is ▮` offers article/dataset/… instead of only "unknown".
    2. **Sectioned-menu sibling** (#357) — after `type is article or ▮`, the post-
       connective FIELD context's `sibling` gets `sibling.values` so the editor's
       "add another <field> value" section can list them for the auto-paren rewrite."""
    entity = result.get("entity")
    ctx = result.get("context") or {}
    if ctx.get("value_kind") in ("enum", "id"):
        slugs = _enum_slugs(ctx.get("column"), entity)
        if slugs:
            ctx["suggestions"] = slugs + (ctx.get("suggestions") or [])
    sib = ctx.get("sibling")
    if sib and sib.get("value_kind") in ("enum", "id"):
        sib_slugs = _enum_slugs(sib.get("column"), entity)
        if sib_slugs:
            sib["values"] = sib_slugs
    return result


@blueprint.route("/parse-context", methods=["GET"])
def parse_context_route():
    """Resolve the grammar context at a cursor offset for editor autocomplete.

    Always 200 — an in-progress query is *defined* by being incomplete, so this
    endpoint never 4xxs. Returns {entity, context:{category, prefix, replace_range,
    value_kind, field, autocomplete_entity, operators, suggestions}, diagnostic}.

    Suggestion lists come from the OQL engine's own field registry (everything it
    will actually parse) — deliberately NOT the broader `/properties` catalog, so the
    editor never offers a field the parser would then reject. Widening OQL field
    coverage + wiring `/properties` here is a follow-up gated on the engine's
    `_FIELDS` growing to match (#363).
    """
    q = request.args.get("q", "")
    pos_arg = request.args.get("pos")
    pos = None
    if pos_arg not in (None, ""):
        try:
            pos = int(pos_arg)
        except (TypeError, ValueError):
            pos = None
    return jsonify(_enrich_enum_suggestions(_parse_context(q, pos))), 200


@blueprint.route("/validate", methods=["GET"])
def validate_oql_route():
    """Validate an OQL string for editor linting.

    A dedicated `?q=` param (not the `/query/oql/<path>` route) because in-progress
    editor text contains `/ ? &` and spaces that don't survive a path segment.
    Always 200; the verdict is in the body.

    Returns {valid, oql (canonical), oqo, oxurl, diagnostics:[{code, message, fixit,
    severity, start, end, location}]}. Both layers flow through the shared
    `diagnostics` registry: parse errors carry the engine's rich OQLError (code +
    fix-it + byte position); validation errors carry the property-catalog
    ValidationError (code + OQO location) plus the registry's fix-it + severity.

    `diagnostics` can hold MORE THAN ONE entry: on a parse failure the engine
    re-parses in recover mode and reports every clause-level error in the doc (not
    just the first), so the editor can squiggle the whole document at once.
    """
    oql = request.args.get("q", "")
    # Parse with the engine directly (preserves code + fixit + position that
    # oql_parser.parse_oql_to_oqo flattens away). The happy path stays on strict
    # `parse()` so a valid query is byte-identical to production parsing.
    try:
        oqo = _engine_parse(oql)
    except _OQLError:
        # The query is broken — re-run in recover mode to collect EVERY clause-level
        # parse error, so the editor squiggles the whole doc instead of just the first
        # error (oxjob #363, multi-error /validate). Always 200; verdict in the body.
        _oqo, diags = _engine_parse_collecting(oql)
        return jsonify(_parse_error_body([parse_diagnostic(d) for d in diags])), 200
    except Exception as e:  # any other engine failure -> one generic diagnostic
        return jsonify(_parse_error_body(
            [parse_diagnostic(_OQLError("OQL_PARSE_ERROR", str(e)))])), 200

    vr = validate_oqo(oqo)
    # Validator errors/warnings flow through the shared registry, so they pick up the
    # canonical fix-it + severity their (type, message, location) shape never carried.
    # #474: also resolve each location to the offending node's decimal address (path).
    from query_translation.oql_render_v2 import (  # lazy: avoid import cycle
        oqo_location_addresses, address_for_location,
    )
    # The addressing tree only annotates diagnostics — skip the build on a clean
    # document (the common lint case).
    loc_addr = oqo_location_addresses(oqo) if (vr.errors or vr.warnings) else {}
    diagnostics = [
        validation_diagnostic(er.type, er.message, er.location,
                              address_for_location(loc_addr, er.location)).to_dict()
        for er in vr.errors
    ] + [
        validation_diagnostic(w.type, w.message, w.location,
                              address_for_location(loc_addr, w.location)).to_dict()
        for w in vr.warnings
    ]

    from query_translation.views import render_all_formats  # lazy: avoid import cycle
    formats = render_all_formats(oqo, vr)
    return jsonify({
        "valid": vr.valid,
        "oql": formats.get("oql"),
        "oqo": formats.get("oqo", oqo.to_dict()),
        "oxurl": formats.get("oxurl"),
        "diagnostics": diagnostics,
    }), 200


def _parse_error_body(diags):
    """Body for a query that failed to parse. ``diags`` is a list of ``Diagnostic``
    (multi-error recovery may report more than one); a clean parse never reaches here.
    Defensive: if recovery somehow collected nothing, still report a generic error so
    the response is never a silent "valid: false, diagnostics: []"."""
    if not diags:
        diags = [parse_diagnostic(_OQLError("OQL_PARSE_ERROR", "could not parse query"))]
    return {
        "valid": False, "oql": None, "oqo": None, "oxurl": None,
        "diagnostics": [d.to_dict() for d in diags],
    }
