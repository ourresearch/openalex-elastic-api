"""Entity registry — the declarative catalog of OpenAlex entity types.

Sourced from ``config/<entity>.yaml`` (the same files the renderer reads for
closed-vocab display names; the server twin of openalex-gui's
``entityConfigs.js``). This is the SIBLING of the property registry
(``core/properties.py``): a :class:`~core.fields.Property` carries an
``entity_type`` string, and THIS registry is what that string resolves against.
Properties describe *columns*; this describes the entity *types* those columns
point at — different cardinality, so it lives next door rather than folded in.

Today it surfaces each entity's ID *shape*, which is the single declarative
source for OQL value-domain validation **Tier 2**: an ``openalex_id``-typed
filter value must carry the right entity prefix, so ``institution is W5`` (a
Works ID on an Institutions filter) is a hard ``invalid_value`` error. The shape
comes straight from each yaml's ``idRegex`` — the native-entity set and their
prefixes are *derived* from that declaration, never hand-listed here, so there is
no parallel table to drift. Room to grow (display_name / icon / native flag / an
``/entities`` endpoint mirroring ``/properties``) as needs arise. (oxjob #363.)
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional, Pattern

try:
    import yaml as _yaml
except Exception:  # pragma: no cover - yaml is a prod dep, but stay defensive
    _yaml = None

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"
)

# A *native* OpenAlex-ID entity's idRegex captures a one-letter prefix + digits,
# e.g. institutions' ``(i\d+)`` or works' ``(w\d+)``. This pulls that prefix out
# of the DECLARED idRegex, so the native-entity set + their prefixes are derived
# from config — not a second prefix list to keep in sync. Non-native idRegex
# (``([a-zA-Z]{2})`` for countries, ``(\d+)`` for fields, slugs for keywords)
# don't match, so those entities get no shape and are never shape-checked.
_NATIVE_PREFIX_RE = re.compile(r"\(\s*([A-Za-z])\\d\+\s*\)")


@dataclass(frozen=True)
class EntityType:
    """One OpenAlex entity type, projected from ``config/<name>.yaml``."""

    name: str
    id_regex: Optional[str] = None      # raw ``idRegex`` string ("" / None if absent)
    id_prefix: Optional[str] = None     # uppercase native prefix (I, A, W, …) or None
    _shape: Optional[Pattern] = None    # compiled anchored matcher (native only)

    @property
    def is_native_id(self) -> bool:
        """True for entities with a single-letter OpenAlex-ID prefix (works,
        authors, institutions, sources, publishers, funders, topics, concepts,
        awards) — the open ID entities OQL Tier-2 shape-checks. False for closed
        vocabs and slug/numeric-id entities."""
        return self.id_prefix is not None

    def id_shape_ok(self, value: object) -> bool:
        """True if ``value`` has this entity's native ID shape (anchored,
        case-insensitive; OpenAlex URL/path prefixes tolerated, mirroring the
        engine's own ``normalize_openalex_id``). A non-native entity has no shape
        → always True (nothing to check)."""
        if self._shape is None:
            return True
        return isinstance(value, str) and self._shape.match(value.strip()) is not None


def _compile_shape(id_regex: str) -> Optional[Pattern]:
    """Anchored, case-insensitive matcher built from a config ``idRegex``. The
    config form carries a leading inline ``(?i)`` and an unanchored capture; we
    strip the inline flag (Python 3.10 rejects a non-leading global flag once the
    pattern is wrapped) and re-apply IGNORECASE over the whole anchored pattern,
    so a bare short id (``I5``) and an OpenAlex URL/path form both match but a
    wrong-prefix id (``W5`` on institutions) does not."""
    body = id_regex[4:] if id_regex.startswith("(?i)") else id_regex
    try:
        return re.compile(rf"(?:{body})\Z", re.IGNORECASE)
    except re.error:  # pragma: no cover - a malformed idRegex must not 500 a query
        return None


def _build() -> Dict[str, EntityType]:
    """Project every ``config/*.yaml`` into an :class:`EntityType`, keyed by its
    ``id`` field (== entity_type for the native entities)."""
    out: Dict[str, EntityType] = {}
    if _yaml is None:  # pragma: no cover - yaml is a prod dep
        return out
    for path in sorted(glob.glob(os.path.join(_CONFIG_DIR, "*.yaml"))):
        try:
            with open(path) as fh:
                doc = _yaml.safe_load(fh) or {}
        except Exception:  # pragma: no cover - missing/corrupt config
            continue
        name = doc.get("id") or os.path.splitext(os.path.basename(path))[0]
        id_regex = doc.get("idRegex") or None
        prefix = shape = None
        if id_regex:
            m = _NATIVE_PREFIX_RE.search(id_regex)
            if m:
                prefix = m.group(1).upper()
                shape = _compile_shape(id_regex)
        out[name] = EntityType(
            name=name, id_regex=id_regex, id_prefix=prefix, _shape=shape
        )
    return out


_ENTITIES: Optional[Dict[str, EntityType]] = None


def _registry() -> Dict[str, EntityType]:
    global _ENTITIES
    if _ENTITIES is None:
        _ENTITIES = _build()
    return _ENTITIES


def get_entity_type(name: Optional[str]) -> Optional[EntityType]:
    """The :class:`EntityType` for an ``entity_type`` string (e.g. a
    ``Property.entity_type``), or None if unknown."""
    if not name:
        return None
    return _registry().get(name)


def entity_for_id_prefix(prefix: Optional[str]) -> Optional[str]:
    """Reverse lookup: the entity_type whose native ID prefix is ``prefix``
    (case-insensitive). Used to name the *wrong* type in a Tier-2 fix-it —
    ``W5`` → ``works``. None if no native entity claims that letter."""
    if not prefix:
        return None
    p = prefix.upper()
    for ent in _registry().values():
        if ent.id_prefix == p:
            return ent.name
    return None


def native_id_entities() -> Dict[str, EntityType]:
    """All entities with a native single-letter ID prefix (the Tier-2 set)."""
    return {n: e for n, e in _registry().items() if e.is_native_id}
