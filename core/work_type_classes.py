"""Which work types are traditional scholarly works (`is_traditional`, oxjob #2064).

Jason and Kyle decided a yes/no `is_traditional` per work type (5-6 Nov 2026, charter plans/worktype.md § 2):
the kinds of works the scholarly record has long counted (articles, books, chapters, theses, conference
papers...). It is not "peer-reviewed": preprints, editorials and letters are traditional. The calls come from
#1647's "Every type's default class" table (team calls, 22 Oct), with paratext moved to non-traditional (5 Nov).

This list is what the works filter `is_traditional:true|false` expands to (a terms query on `type`, so no
reindex) and what each work object's `is_traditional` is computed from at serialization. /types serves the same
value from `openalex.common.work_types.is_traditional` (Databricks, synced to work-types-v1); a test keeps every
type in config/work-types.yaml in exactly one of the two sets below, so a new type can't ship unclassified.
"""

# ┌─ CHANGING THIS LIST? RE-SYNC THE WORKS INDEX BOOLEAN (oxjob #2065) ─────────────────────────────┐
# │ The default works view hides `is_non_traditional_child:true` (core/default_view.py), a boolean │
# │ walden's notebooks/elastic/sync_works writes from openalex.common.work_types.is_traditional:   │
# │ true when a work has a parent and its type is NOT in this list. Move a type in or out here and │
# │ that boolean is wrong on every child of that type until Databricks' work_types table has the   │
# │ same change AND those works are re-synced. Until then the default view hides or shows the      │
# │ wrong works while `is_traditional:` (read from this list at query time) says otherwise.        │
# │ Check: `PYTHONPATH=. venv/bin/python scripts/check_default_view_fold.py` (the two counts must  │
# │ match).                                                                                        │
# └────────────────────────────────────────────────────────────────────────────────────────────────┘
TRADITIONAL_TYPES = frozenset({
    "article",
    "book",
    "book-chapter",
    "book-review",
    "conference-paper",
    "data-paper",
    "dissertation",
    "editorial",
    "erratum",
    "letter",
    "preprint",
    "retraction",
    "review",
    "software-paper",
})

NON_TRADITIONAL_TYPES = frozenset({
    "conference-abstract",
    "dataset",
    "other",
    "paratext",
    "peer-review",
    "reference-entry",
    "report",
    "software",
    "standard",
    "supplementary-materials",
    # added to the vocabulary by oxjob #2063 (classified here so the two can ship in either order)
    "study-registration",
    # retired 7 Nov 2026 (oxjob #1647); classified until its works are gone
    "libguides",
})


def is_traditional(work_type):
    """True / False for a work's `type`; None when the work has no type. A type outside both sets counts as
    not traditional, exactly as the filter's `false` (every type that isn't traditional) does."""
    if not work_type:
        return None
    return str(work_type).lower() in TRADITIONAL_TYPES
