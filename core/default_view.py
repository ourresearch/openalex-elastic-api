"""The works default view leaves out pieces of other works (oxjob #2065, step 2; Jason, 7 Nov 2026).

A work that has a parent and is not a traditional scholarly work (book front matter, an
encyclopedia entry, a figure, a file, one record of a data series) is hidden by default:

    hidden = has_parent_work:true AND is_traditional:false

Nothing else decides it: not the relationship, not whether the work has children, not citations.
There is no public word, field or filter for "hidden": `corpus=all` minus
`has_parent_work:true,is_traditional:false` reproduces it.

The query reads ONE internal boolean in the works index, HIDDEN_PIECE_FIELD, which walden's
sync_works writes: true exactly when the work has a parent and its type is not traditional, absent
or false otherwise (a doc without the field is not hidden). Reading the two public filters on
every works query cost about 100 ms on a whole-corpus count (measured 13 Nov 2026 on a 26M-work
stand-in field); one term costs nothing measurable. The boolean is a fold of the public rule,
not a second rule: `hidden_by_public_filters_query` is that rule, a unit test states the
equivalence, and scripts/check_default_view_fold.py compares the two counts on the live index
(run it after a backfill and whenever TRADITIONAL_TYPES changes).

It rides with the core corpus: `corpus=core` (the /works default) leaves hidden pieces out;
`corpus=all` and `corpus=expansion` don't apply it. A filter on a parent-child column brings the
pieces back and leaves the corpus as it is. /works/W... is never filtered.
"""
from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError

# Filters that ask about parents and children: any of them lifts the rule. Matched as WHOLE keys.
# A substring test (as `'is_xpac:' in filter` is) would also fire on
# authorships.institutions.lineage and the other *lineage filters, and show hidden pieces in
# every institution query.
PIECE_FILTER_KEYS = frozenset({"has_parent_work", "parent_works.id", "parent_works.relationship", "lineage"})

# How the rule travels in a parsed filter list (the `default_filters` of core.shared_view), beside
# `{"is_xpac": "false"}`. Internal: core.filter applies it, core.utils.map_filter_params refuses it
# in a request, and it is in no fields_dict, so /properties, OQL and OQO never see it.
HIDDEN_PIECES_KEY = "_default.hide_pieces"
HIDE_PIECES_FILTER = {HIDDEN_PIECES_KEY: "true"}


# The works-index boolean the default view reads. Internal: not in the work record, not a filter,
# not in /properties, OQL or OQO. Walden writes it (notebooks/elastic/sync_works). The one place
# the name is spelled.
HIDDEN_PIECE_FIELD = "is_non_traditional_child"


def visible_works_query():
    """Works the default view keeps: every work that is not a hidden piece."""
    return Q("bool", must_not=[Q("term", **{HIDDEN_PIECE_FIELD: True})])


def hidden_by_public_filters_query():
    """The hidden set as the public rule states it: has_parent_work:true AND is_traditional:false,
    from those two filters' own queries. HIDDEN_PIECE_FIELD must be true on exactly these works
    (tests/unit/test_default_view.py; scripts/check_default_view_fold.py checks the live index)."""
    from works.fields import fields_dict  # here: works.fields imports core at load time

    has_parent = fields_dict["has_parent_work"].query_for("true")
    not_traditional = fields_dict["is_traditional"].query_for("false")
    return Q("bool", filter=[has_parent, not_traditional])


def lifts_hiding(filter_keys):
    """True when any filter key is exactly a parent-child column (hyphens read as underscores)."""
    return any((key or "").replace("-", "_") in PIECE_FILTER_KEYS for key in filter_keys)


def filter_keys(filter_params):
    """The keys of a parsed filter list ([{key: value}, ...] or None)."""
    return [key for clause in (filter_params or []) for key in clause]


def request_filter_params(filter_string):
    """A raw `filter=` string as a parsed filter list; empty when it doesn't parse (the view that
    runs the request answers the 400)."""
    from core.utils import map_filter_params

    try:
        return map_filter_params(filter_string) or []
    except APIQueryParamsError:
        return []


def request_filter_keys(filter_string):
    return filter_keys(request_filter_params(filter_string))


def _names_expansion(filter_params):
    """A legacy `is_xpac:true` filter (the expansion corpus alone, as corpus=expansion)."""
    values = [str(value).strip().strip('"').lower() for clause in (filter_params or [])
              for key, value in clause.items() if key.replace("-", "_") == "is_xpac"]
    return any(v in ("true", "!false") for v in values)


def hides_pieces(corpus, include_xpac, filter_params):
    """Whether a works request leaves hidden pieces out.

        corpus: the `corpus=` value, or None when absent
        include_xpac: the legacy flag is true (it means corpus=all)
        filter_params: the request's parsed filter list
    """
    if corpus is not None:
        core = corpus.strip().lower() == "core"
    else:
        core = not include_xpac and not _names_expansion(filter_params)
    return core and not lifts_hiding(filter_keys(filter_params))
