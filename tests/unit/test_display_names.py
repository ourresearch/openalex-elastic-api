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
        # a param guaranteed absent from the curated override map → humanize default
        assert resolve_display_name("works", "totally_made_up_param") == (
            "totally made up param",
            [],
        )
        assert resolve_display_name("nonsuch_entity", "x_y") == ("x y", [])

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
        # Same param, different entity — curated to distinct canonical labels.
        assert resolve_display_name("works", "display_name")[0] == "title"
        assert resolve_display_name("authors", "display_name")[0] == "name"


class TestSeededOverrides:
    """Lock in representative Phase 2 reconciliation decisions (2026-06-06)."""

    def test_canonical_labels(self):
        cases = {
            ("works", "publication_year"): "year",
            ("works", "authorships.author.id"): "author",
            ("works", "primary_topic.id"): "topic",
            ("works", "ids.openalex"): "openalex id",  # exception: GUI "Work" rejected
            ("works", "open_access.oa_status"): "open access status",  # GUI wins
            ("works", "primary_location.source.is_in_doaj"): "indexed by DOAJ",
            ("sources", "apc_usd"): "article processing charge",
        }
        for (entity, param), expected in cases.items():
            assert resolve_display_name(entity, param)[0] == expected

    def test_acronym_casing_preserved(self):
        # lowercased except acronyms the GUI wrote in caps / mixed
        assert resolve_display_name("works", "authorships.author.orcid")[0] == "ORCID"
        assert resolve_display_name("works", "doi_starts_with")[0] == "DOI prefix"
        assert resolve_display_name("works", "has_pmid")[0] == "indexed by PubMed"

    def test_oql_aliases_attached(self):
        _, aliases = resolve_display_name("works", "cited_by_count")
        assert "cited by count" in aliases

    def test_citation_family_unified_across_entities(self):
        # #381 consistency gate: cited_by_count is "citation count" (singular) on
        # EVERY entity, via the global-by-param override — not just works, and not
        # the humanized "cited by count" on the long tail.
        for entity in ("works", "authors", "funders", "sources", "sdgs",
                       "institutions", "topics", "countries"):
            label, aliases = resolve_display_name(entity, "cited_by_count")
            assert label == "citation count", entity
            assert "cited by count" in aliases, entity

    def test_references_family_labels(self):
        # outgoing references use the field-standard words; old spellings stay as
        # back-compat OQL-parse aliases.
        assert resolve_display_name("works", "referenced_works") == (
            "references", ["referenced works"])
        assert resolve_display_name("works", "referenced_works_count") == (
            "reference count", ["references count"])

    def test_relationship_filters_unchanged(self):
        # the COUNT word ("citation count") must stay distinct from the
        # RELATIONSHIP filters, which keep their own words (no system reuses one).
        assert resolve_display_name("works", "cited_by")[0] == "cited by"
        assert resolve_display_name("works", "cites")[0] == "cites"

    def test_per_entity_override_beats_global(self):
        # global-by-param is a fallback; a per-entity override still wins.
        from core.display_names import (
            DISPLAY_NAME_OVERRIDES,
            GLOBAL_DISPLAY_NAME_OVERRIDES,
        )

        assert "cited_by_count" in GLOBAL_DISPLAY_NAME_OVERRIDES
        # seed a hypothetical per-entity override and confirm it takes precedence
        DISPLAY_NAME_OVERRIDES.setdefault("works", {})
        sentinel = DISPLAY_NAME_OVERRIDES["works"].get("cited_by_count")
        DISPLAY_NAME_OVERRIDES["works"]["cited_by_count"] = {"display_name": "ZZZ"}
        try:
            assert resolve_display_name("works", "cited_by_count")[0] == "ZZZ"
        finally:
            if sentinel is None:
                del DISPLAY_NAME_OVERRIDES["works"]["cited_by_count"]
            else:
                DISPLAY_NAME_OVERRIDES["works"]["cited_by_count"] = sentinel

    def test_works_freetext_labels_from_374(self):
        # #374 shipped → the broad search keys take its final labels (Phase 4).
        assert resolve_display_name("works", "fulltext.search")[0] == "full text"
        assert resolve_display_name("works", "title_and_abstract.search")[0] == "title/abstract"

    def test_phase4_reconciliation(self):
        # de-paren + reconciliation (#381 Phase 4)
        cases = {
            ("works", "is_xpac"): "in extended index",
            ("works", "locations.source.id"): "any location source",
            ("works", "raw_affiliation_strings"): "exact raw affiliation",
            ("works", "apc_paid.value_usd"): "estimated APC paid",
            ("fields", "domain.id"): "parent domain",
            ("topics", "siblings"): "sibling topics",
            ("domains", "fields"): "child fields",
            # bucket-1 fixes (registry adopts the GUI word)
            ("authors", "display_name_alternatives"): "observed names",
            ("awards", "display_name"): "title",
            # alias key-mismatch fold-in: the server param gets the GUI label
            ("authors", "orcid"): "ORCID",
            ("institutions", "ror"): "ROR",
            ("sources", "host_organization"): "publisher",
        }
        for (entity, param), expected in cases.items():
            assert resolve_display_name(entity, param)[0] == expected, (entity, param)


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

    def test_display_name_and_aliases_in_public_contract(self):
        """Phase 3: display_name + aliases are part of the public /properties wire
        form (v1.3.0). aliases are sorted for fingerprint stability."""
        from core.properties import get_property

        ser = get_property("works", "cited_by_count").serialize()
        assert set(ser) == {
            "name", "type", "operators", "actions", "entity_type",
            "display_name", "aliases",
        }
        assert ser["display_name"] == "citation count"
        assert ser["aliases"] == sorted(ser["aliases"])
