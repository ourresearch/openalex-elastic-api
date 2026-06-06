"""#381 Phase 1 — canonical property display names.

Covers the resolution mechanism (humanize + override) and two invariants:
  * every property in the live catalog resolves a non-empty `display_name`;
  * `display_name`/`aliases` are NOT yet in the public `serialize()` payload
    (that is Phase 3, gated on a MAJOR PROPERTIES_VERSION bump) — so Phase 1
    must not move the `/properties` snapshot/fingerprint at all.
"""

from core.display_names import (
    DISPLAY_NAME_OVERRIDES,
    humanize,
    resolve_display_name,
)


class TestHumanize:
    def test_underscores_become_spaces(self):
        assert humanize("publication_year") == "publication year"

    def test_strips_search_suffix(self):
        assert humanize("title_and_abstract.search") == "title and abstract"
        assert humanize("default.search.exact") == "default"

    def test_dots_become_spaces(self):
        assert humanize("summary_stats.h_index") == "summary stats h index"

    def test_always_non_empty_for_non_empty_param(self):
        for param in ("a", "x.y", "is_oa", "authorships.author.id"):
            assert humanize(param)


class TestResolve:
    def test_falls_back_to_humanize_with_empty_aliases(self):
        assert resolve_display_name("works", "publication_year") == (
            "publication year",
            [],
        )

    def test_override_wins(self, monkeypatch):
        monkeypatch.setitem(
            DISPLAY_NAME_OVERRIDES,
            "works",
            {"display_name.search": {"display_name": "title", "aliases": ["title"]}},
        )
        assert resolve_display_name("works", "display_name.search") == (
            "title",
            ["title"],
        )

    def test_override_returns_a_fresh_alias_list(self, monkeypatch):
        """aliases must be copied, so callers can't mutate the override table."""
        monkeypatch.setitem(
            DISPLAY_NAME_OVERRIDES,
            "works",
            {"x": {"display_name": "X", "aliases": ["a"]}},
        )
        _, aliases = resolve_display_name("works", "x")
        aliases.append("b")
        assert DISPLAY_NAME_OVERRIDES["works"]["x"]["aliases"] == ["a"]

    def test_entity_aware(self):
        # Same param, different entity — both resolve (humanized today; Phase 2
        # gives them distinct curated labels "title" vs "name").
        assert resolve_display_name("works", "display_name")[0]
        assert resolve_display_name("authors", "display_name")[0]


class TestCatalogInvariants:
    def test_every_property_has_a_display_name(self):
        from core.properties import ENTITY_PROPERTIES, _merged_properties

        missing = [
            (entity, name)
            for entity in ENTITY_PROPERTIES
            for name, prop in _merged_properties(entity).items()
            if not prop.display_name
        ]
        assert not missing, f"properties with no display_name: {missing[:20]}"

    def test_display_name_not_yet_in_public_contract(self):
        """Phase 1 invariant: the public wire form is unchanged, so the snapshot
        and fingerprint can't move (no version bump in Phase 1)."""
        from core.properties import ENTITY_PROPERTIES

        prop = next(iter(next(iter(ENTITY_PROPERTIES.values())).values()))
        keys = set(prop.serialize())
        assert "display_name" not in keys
        assert "aliases" not in keys
        assert keys == {"name", "type", "operators", "actions", "entity_type"}
