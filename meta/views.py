"""``/meta`` — the unified metadata catalog (oxjob #405).

ONE catalog tree describing what OpenAlex *is queryable about*: the entity types
and, hanging off each, its queryable properties. Two source layers, deliberately
NOT merged (see #405 / PLAN.md):

  * **entities** — authored, entity-level curation, served from the entity
    registry (:mod:`core.entities`, sourced from the trimmed ``config/*.yaml``);
  * **properties** — *derived* from the live ``Field`` objects
    (:func:`core.properties.render_properties`), preserving the #331 no-drift
    guarantee and the published, versioned ``/properties`` contract.

The whole catalog lives under a dedicated ``/meta`` namespace, disjoint from the
data tree (``/works``, ``/authors/A123``, …) — so the per-entity properties route
(``/meta/entities/<e>/properties``) does NOT collide with the universal
entity-by-id route ``/entities/<e>/<path:id>`` (the collision that kept
``/properties`` flat; #331 Decision G). The properties sub-resource reuses
``render_properties`` verbatim — there is exactly ONE properties source and ONE
drift gate; ``/properties`` (+ ``/properties/<e>``) stays as the established
top-level alias.

    GET /meta                                          catalog root (links)
    GET /meta/entities                                 all entity types (summary)
    GET /meta/entities/<entity>                        one entity type (detail)
    GET /meta/entities/<entity>/properties             == /properties/<entity>
    GET /meta/entities/<entity>/properties/<property>  one property object

Nesting stops at ``properties/<property>``: a property's ``type``/``operators``/
``actions``/``display_name``/``aliases`` are *fields* of the property object, not
further routes (endpoint-namespace research, PLAN.md Notes).
"""

from flask import Blueprint, jsonify

from core.entities import all_entity_types, get_entity_type
from core.properties import PROPERTIES_VERSION, render_properties

blueprint = Blueprint("meta", __name__)


def _error(message, error_type, status=404):
    """A plain REST-style error for the ``/meta`` tree. (The OQO validator's
    validation-wrapped error shape is specific to the translation endpoints; a
    read-only catalog 404 doesn't need it.)"""
    return jsonify({"error": {"type": error_type, "message": message}}), status


def _id_format(ent):
    """The entity's OpenAlex-ID shape, or None when the entity declares no
    ``idRegex``. ``native`` is the *derived* single-letter-prefix flag the OQL
    Tier-2 shape check keys off (distinct from the authored ``is_native``)."""
    if not ent.id_regex:
        return None
    return {
        "regex": ent.id_regex,
        "prefix": ent.id_prefix,      # uppercase native letter (W, A, …) or None
        "native": ent.is_native_id,   # derived from the prefix; see core.entities
    }


def _entity_summary(ent):
    """List-level entry: identity, display names, description, ID format, and a
    link to the entity's properties sub-resource."""
    return {
        "id": ent.name,
        "display_name": ent.display_name,
        "display_name_singular": ent.display_name_singular,
        "description": ent.description,
        "id_format": _id_format(ent),
        "properties_url": f"/meta/entities/{ent.name}/properties",
    }


def _entity_detail(ent):
    """Full entry: the summary plus the remaining curated entity-level facts —
    the authored native flag, alternate names, and the closed-vocabulary
    ``values`` list (None for open/native entities)."""
    detail = _entity_summary(ent)
    detail.update(
        {
            "is_native": ent.is_native,
            "alternate_names": list(ent.alternate_names),
            "values": ent.values,
        }
    )
    return detail


@blueprint.route("/meta", methods=["GET"])
def meta_root():
    """Catalog root: a singleton pointing at the entity collection and naming the
    published properties-contract version (so a client can detect drift without
    fetching the whole tree)."""
    entities = all_entity_types()
    return jsonify(
        {
            "description": (
                "OpenAlex metadata catalog: the entity types and, hanging off "
                "each, its queryable properties."
            ),
            "entities_url": "/meta/entities",
            "entity_count": len(entities),
            "properties_version": PROPERTIES_VERSION,
        }
    ), 200


@blueprint.route("/meta/entities", methods=["GET"])
def meta_entities():
    """All entity types (summary form), sorted by id."""
    entities = all_entity_types()
    return jsonify(
        {
            "meta": {"count": len(entities)},
            "results": [_entity_summary(ent) for ent in entities.values()],
        }
    ), 200


@blueprint.route("/meta/entities/<entity>", methods=["GET"])
def meta_entity(entity):
    """One entity type's full catalog entry."""
    ent = get_entity_type(entity)
    if ent is None:
        return _error(f"'{entity}' is not a known entity type.", "invalid_entity")
    return jsonify(_entity_detail(ent)), 200


@blueprint.route("/meta/entities/<entity>/properties", methods=["GET"])
def meta_entity_properties(entity):
    """The entity's queryable properties — the SAME payload as ``/properties/<e>``
    (reuses :func:`render_properties`; one source, one drift gate). 404s on an
    entity the registry doesn't know, so ``/meta`` stays scoped to browsable
    entity types (properties-only keys like ``locations`` are reachable via
    ``/properties`` but are not ``/meta`` entities)."""
    if get_entity_type(entity) is None:
        return _error(f"'{entity}' is not a known entity type.", "invalid_entity")
    return jsonify(render_properties(entity=entity)), 200


@blueprint.route("/meta/entities/<entity>/properties/<property_name>", methods=["GET"])
def meta_entity_property(entity, property_name):
    """One property object (``type``/``operators``/``actions``/``entity_type``/
    ``display_name``/``aliases``). Sliced from the same rendered payload as the
    list route, so the single-property view can't disagree with the collection."""
    if get_entity_type(entity) is None:
        return _error(f"'{entity}' is not a known entity type.", "invalid_entity")
    props = render_properties(entity=entity)["properties"].get(entity, {})
    prop = props.get(property_name)
    if prop is None:
        return _error(
            f"'{property_name}' is not a known property of '{entity}'.",
            "invalid_property",
        )
    return jsonify(prop), 200
