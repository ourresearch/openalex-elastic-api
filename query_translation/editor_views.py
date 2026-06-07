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
from query_translation.oql_lang import parse as _engine_parse
from query_translation.validator import validate_oqo

blueprint = Blueprint("oql_editor", __name__)


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
    return jsonify(_parse_context(q, pos)), 200


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
    """
    oql = request.args.get("q", "")
    # Parse with the engine directly (preserves code + fixit + position that
    # oql_parser.parse_oql_to_oqo flattens away).
    try:
        oqo = _engine_parse(oql)
    except _OQLError as e:
        return jsonify(_parse_error_body(parse_diagnostic(e))), 200
    except Exception as e:  # any other engine failure -> one generic diagnostic
        return jsonify(_parse_error_body(
            parse_diagnostic(_OQLError("OQL_PARSE_ERROR", str(e))))), 200

    vr = validate_oqo(oqo)
    # Validator errors/warnings flow through the shared registry, so they pick up the
    # canonical fix-it + severity their (type, message, location) shape never carried.
    diagnostics = [
        validation_diagnostic(er.type, er.message, er.location).to_dict()
        for er in vr.errors
    ] + [
        validation_diagnostic(w.type, w.message, w.location).to_dict()
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


def _parse_error_body(diag):
    return {
        "valid": False, "oql": None, "oqo": None, "oxurl": None,
        "diagnostics": [diag.to_dict()],
    }
