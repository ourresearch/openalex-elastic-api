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

The switch is `include_parts=true` (Jason, 15 Nov 2026, decision 4a in plans/retractions.md: one
parameter per kind of work the default leaves out, tied to a use case; `include_pulled` is the
second, at the end of this module). It brings the pieces back and changes nothing else: the corpus stays whatever it was.
Every door that applies the rule reads it: /works (list, search, group_by), /v2/works,
/works/filters, /works/stats, /autocomplete and the OQO executor (query_translation/execution.py).

Until #2264 moves the corpus to the expansion alone, the rule still rides with the core corpus as
well: `corpus=core` (the /works default) leaves hidden pieces out; `corpus=all` and
`corpus=expansion` don't apply it. A filter on a parent-child column brings the pieces back and
leaves the corpus as it is. /works/W... is never filtered.
"""
from elasticsearch_dsl import Q

from core.exceptions import APIQueryParamsError

# Pulled works (oxjob #2264) are the second kind the default view leaves out; their section is at the end.

# The switch that brings the pieces back, in both spellings the other parameters take.
PARTS_PARAMS = ("include_parts", "include-parts")


def _flag_value(value, name, what):
    """True or False for an include_* value, in any case; a JSON 400 naming `what` it brings back otherwise."""
    v = (value or "").strip().strip('"').lower()
    if v == "true":
        return True
    if v in ("false", ""):
        return False
    raise APIQueryParamsError(f"{name} takes true or false, not '{value}'. {what}")


def parts_flag_value(value, name="include_parts"):
    """True or False for an include_parts value, in any case; a JSON 400 for anything else."""
    return _flag_value(value, name, "include_parts=true brings back pieces of other works (figures, book front "
                                    "matter, single records of a data series) that the default view leaves out.")


def include_parts_requested(args):
    """True when request args ask for pieces of other works. Every value given is checked, so
    include_parts=banana answers a 400 even beside include-parts=true."""
    flags = [parts_flag_value(args.get(name), name) for name in PARTS_PARAMS if args.get(name) is not None]
    return any(flags)

# Filters that ask about parents and children: any of them lifts the rule. Matched as WHOLE keys.
# A substring test (as `'is_xpac:' in filter` is) would also fire on
# authorships.institutions.lineage and the other *lineage filters, and show hidden pieces in
# every institution query.
# parent_works.link_type is the new name of parent_works.relationship (oxjob #2481).
PIECE_FILTER_KEYS = frozenset({"has_parent_work", "parent_works.id", "parent_works.relationship",
                               "parent_works.link_type", "lineage"})

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


def _names_any(keys, key_set):
    """True when any key is exactly one of key_set (hyphens read as underscores)."""
    return any((key or "").replace("-", "_") in key_set for key in keys)


def lifts_hiding(filter_keys):
    """True when any filter key is exactly a parent-child column."""
    return _names_any(filter_keys, PIECE_FILTER_KEYS)


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


def hides_pieces(corpus, include_xpac, filter_params, include_parts=False):
    """Whether a works request leaves hidden pieces out.

        corpus: the `corpus=` value, or None when absent
        include_xpac: the legacy flag is true (it means corpus=all)
        filter_params: the request's parsed filter list
        include_parts: the request says include_parts=true
    """
    if include_parts:
        return False
    if corpus is not None:
        core = corpus.strip().lower() == "core"
    else:
        core = not include_xpac and not _names_expansion(filter_params)
    return core and not lifts_hiding(filter_keys(filter_params))


# ── Pulled works (oxjob #2264) ────────────────────────────────────────────────────────────────────
# Jason, 15 Nov 2026 (oxjobs plans/retractions.md § 5, decisions 3-4a; kept over Kyle's review 16 Nov): works their
# publisher, host or authors retracted, withdrew or removed (`is_pulled`) are left out of every works list, search,
# count and group_by, whatever the corpus. `include_pulled=true` brings them back and changes nothing else. A lookup
# by ID or DOI (/works/W...) always answers, with the flag showing; nothing is deleted; entity counts (works_count,
# h-index) still count pulled works.
#
# Parameters add works, filters subtract (decision 4a, refined): a filter naming is_pulled or is_retracted stays as a
# shortcut, but /works, /v2/works and /works/stats answer it with a redirect to the same URL plus include_pulled=true,
# so the URL says what added the works. Doors with no URL of their own to redirect (/works/filters, autocomplete and
# the OQO executor) read such a filter as include_pulled=true.

# The switch that brings pulled works back, in both spellings the other parameters take.
PULLED_PARAMS = ("include_pulled", "include-pulled")

# Fields that ask about pulled works, so naming one brings them back: in a filter (via the redirect), a group_by (the
# same), or an OQL split or measure (`percent retracted`, `by pulled`). Matched as whole keys.
PULLED_FIELD_KEYS = frozenset({"is_pulled", "is_retracted"})

# How the rule travels in a parsed filter list, beside HIDE_PIECES_FILTER. Internal, like HIDDEN_PIECES_KEY:
# core.filter applies it, core.utils.map_filter_params refuses it in a request.
HIDDEN_PULLED_KEY = "_default.hide_pulled"
HIDE_PULLED_FILTER = {HIDDEN_PULLED_KEY: "true"}

# The works-index boolean (walden sync_works). Only docs re-stamped since night 2026-11-17 carry it, so "not pulled"
# is NOT true, as works.fields' is_pulled:false is.
PULLED_FIELD = "is_pulled"


def pulled_flag_value(value, name="include_pulled"):
    """True or False for an include_pulled value, in any case; a JSON 400 for anything else."""
    return _flag_value(value, name, "include_pulled=true brings back works their publisher, host or authors "
                                    "retracted, withdrew or removed, which the default view leaves out.")


def include_pulled_param(args):
    """The request's include_pulled as True or False, or None when it gives none. Every spelling given is checked."""
    flags = [pulled_flag_value(args.get(name), name) for name in PULLED_PARAMS if args.get(name) is not None]
    return any(flags) if flags else None


def not_pulled_query():
    """Works the default view keeps: every work that is not pulled (what is_pulled:false matches)."""
    return Q("bool", must_not=[Q("term", **{PULLED_FIELD: "true"})])


def names_pulled(keys):
    """True when any key is is_pulled or is_retracted."""
    return _names_any(keys, PULLED_FIELD_KEYS)


def request_group_by_keys(args):
    """The field a request's group_by names (a `:include_unknown` suffix dropped). Not group_bys: the website's
    batched facet counts describe the result set as it stands."""
    value = args.get("group_by") or args.get("group-by") or ""
    return [value.split(":", 1)[0].strip()] if value.strip() else []


def pulled_hidden(args, keys):
    """Whether a works request leaves pulled works out. include_pulled, when given, decides (false keeps them out even
    beside an is_retracted filter: filters only subtract). Without it, any key naming is_pulled / is_retracted brings
    them back; the redirect doors never get here with one. The corpus has no say."""
    asked = include_pulled_param(args)
    return not asked if asked is not None else not names_pulled(keys)


def hides_pulled(args, filter_params):
    """pulled_hidden for a request's parsed filter list and its group_by."""
    return pulled_hidden(args, filter_keys(filter_params) + request_group_by_keys(args))


def pulled_redirect_location(path, query_string, args):
    """Where a works request whose filter or group_by names is_pulled / is_retracted is sent: the same path and query
    string plus include_pulled=true. None when the request already gives include_pulled (true or false; a bad value
    answers a 400 here) or names neither. Relative, so it survives the proxies in front of the API."""
    if include_pulled_param(args) is not None:
        return None
    keys = request_group_by_keys(args)
    filter_string = args.get("filter") or ""
    if "pulled" in filter_string or "retracted" in filter_string:  # parse only when it can matter (every request)
        keys += request_filter_keys(filter_string)
    if not names_pulled(keys):
        return None
    joiner = "&" if query_string else ""
    return f"{path}?{query_string}{joiner}include_pulled=true"


def default_view_query(hide_pieces, hide_pulled):
    """The default view as one query, for the doors that take a base query; None when nothing is hidden."""
    qs = ([visible_works_query()] if hide_pieces else []) + ([not_pulled_query()] if hide_pulled else [])
    if not qs:
        return None
    return qs[0] if len(qs) == 1 else Q("bool", filter=qs)
