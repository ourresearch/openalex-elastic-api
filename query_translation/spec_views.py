"""Read-only routes that serve the canonical OQL/OQO spec artifacts (oxjob #361).

The OQL playground's three spec/reference pages (Guide, Grammar, OQO schema) live
in `openalex-gui` but the canonical artifacts live HERE, in `docs/`. To keep the
pages from drifting from the implementation, the GUI fetches the live artifacts at
runtime from these endpoints rather than bundling a copy:

  GET /query/spec/cheatsheet -> docs/oql-cheatsheet.md      (text/markdown)  one-page OQL cheat sheet
  GET /query/spec/guide      -> docs/oql-guide.md           (text/markdown)  readable OQL guide (BLUF)
  GET /query/spec/api        -> docs/oql-api.md             (text/markdown)  the OQL/OQO HTTP API reference
  GET /query/spec/oql        -> docs/oql-spec.md            (text/markdown)  the frozen normative spec
  GET /query/spec/oqo        -> docs/oqo-schema.json        (application/json) OQO JSON Schema
  GET /query/spec/grammar    -> docs/oql/grammar.ebnf       (text/plain)     derived W3C-EBNF
  GET /query/spec/railroad   -> docs/oql/grammar.railroad.html (XHTML)       rendered railroad
  GET /query/spec            -> {artifacts: [...]}          a tiny index/manifest

These are STATIC FILE READS — they add NO `Field` definitions and touch neither
the property catalog nor Elasticsearch, so they cannot trip the `/properties`
drift gate. Each artifact is itself kept honest by its own gate:
  * oqo-schema.json   — `python -m query_translation.regen_schema --check`
  * grammar.ebnf      — `tests/oql/test_grammar_ebnf.py` (keyword closure vs the
                        parser + corpus tokenization)
  * oql-spec.md       — cases-first; the corpus round-trip is its conformance net.
  * oql-cheatsheet.md / oql-guide.md / oql-api.md — hand-written user docs (no
                        machine gate); every example was prod-verified at
                        authoring (oxjobs #530, #630).

Kept in a SEPARATE blueprint (not `query_translation/views.py`) to stay out of the
in-flight execution/translation reorg in that file, exactly like editor_views.py.
"""
import os

from flask import Blueprint, Response, abort, jsonify

blueprint = Blueprint("oql_spec", __name__)

# Repo root: query_translation/ -> repo root -> docs/
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_REPO, "docs")

# slug -> (relative path under docs/, mimetype). The whole serving surface is this
# allowlist; nothing else under docs/ is reachable (no path params, no traversal).
_ARTIFACTS = {
    "cheatsheet": ("oql-cheatsheet.md", "text/markdown; charset=utf-8"),
    "guide": ("oql-guide.md", "text/markdown; charset=utf-8"),
    "api": ("oql-api.md", "text/markdown; charset=utf-8"),
    "oql": ("oql-spec.md", "text/markdown; charset=utf-8"),
    "oqo": ("oqo-schema.json", "application/json"),
    "grammar": (os.path.join("oql", "grammar.ebnf"), "text/plain; charset=utf-8"),
    "railroad": (os.path.join("oql", "grammar.railroad.html"),
                 "application/xhtml+xml; charset=utf-8"),
}


def _serve(slug):
    rel, mimetype = _ARTIFACTS[slug]
    path = os.path.join(_DOCS, rel)
    if not os.path.exists(path):
        abort(404, description=f"spec artifact '{slug}' not found on server")
    # Read + return rather than send_file so we control the mimetype/charset and
    # CORS (app-wide after_request) applies uniformly; these files are small.
    with open(path, "rb") as fh:
        body = fh.read()
    resp = Response(body, mimetype=mimetype.split(";")[0])
    resp.headers["Content-Type"] = mimetype
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@blueprint.route("/query/spec", methods=["GET"])
def spec_index():
    """Manifest of the available spec artifacts (lets the GUI discover routes)."""
    return jsonify({
        "artifacts": [
            {"slug": slug, "filename": os.path.basename(rel),
             "content_type": mt.split(";")[0], "url": f"/query/spec/{slug}"}
            for slug, (rel, mt) in _ARTIFACTS.items()
        ]
    }), 200


@blueprint.route("/query/spec/<slug>", methods=["GET"])
def spec_artifact(slug):
    """Serve one canonical spec artifact by slug (oql | oqo | grammar | railroad)."""
    if slug not in _ARTIFACTS:
        abort(404, description=f"unknown spec artifact '{slug}'")
    return _serve(slug)
