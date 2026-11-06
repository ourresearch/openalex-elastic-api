"""A works `type` filter value must name a work type (oxjob #1836).

`filter=type:journal-article` used to answer a count of 0 with no message, so a typo, a source's own
label, or a type we retired (29 Jun 2026; libguides 7 Nov 2026) silently emptied a user's results.
Now any value that isn't a work type answers a JSON 400 that says why and what to use. The list of work types is the registry's
(`config/work-types.yaml`, the same list OQL checks against); `null` / `!null` still mean "no type".

Only values a user typed are checked (core/filter.py). Collections (`col_...`) resolve elsewhere.
"""
import difflib
from functools import lru_cache
from typing import NamedTuple, Optional

from core.exceptions import APIQueryParamsError
from core.fields import TermField


class Retired(NamedTuple):
    removed: str                # the day it left the vocabulary
    use: Optional[str] = None   # the type most of its works now carry (each work's primary location raw type, 3 Nov 2026)
    why: Optional[str] = None   # with no such type: why it left, and where to look instead


# Types removed from the vocabulary: the four of 29 Jun 2026 (oxjob #534), and libguides on 7 Nov 2026,
# when library guides left OpenAlex (oxjob #1647, Jason and Kyle, 6 Nov 2026).
RETIRED = {
    "book-section": Retired("29 Jun 2026", use="reference-entry"),
    "database": Retired("29 Jun 2026", use="dataset"),
    "report-component": Retired("29 Jun 2026", use="report"),
    "grant": Retired("29 Jun 2026", why="grants aren't works. Find them at https://api.openalex.org/awards."),
    "libguides": Retired("7 Nov 2026", why="library guides aren't scholarly works, so OpenAlex no longer includes them."),
}

# A source's own label for the kind of work (Crossref's list), mapped to the type most works with that
# primary-location label carry (live group_by, 3 Nov 2026: 85-100% each, posted-content 66% preprint).
# Labels that are also work types (book, dataset, ...) never get here.
SOURCE_LABELS = {
    "journal-article": "article",
    "proceedings-article": "conference-paper",
    "posted-content": "preprint",
    "book-part": "book-chapter",
    "book-track": "book-chapter",
    "monograph": "book",
    "edited-book": "book",
    "book-set": "book",
    "reference-book": "reference-entry",
    "journal-issue": "paratext",
    "journal-volume": "paratext",
    "proceedings": "paratext",
    "proceedings-series": "paratext",
    "book-series": "paratext",
    "report-series": "paratext",
}

# What a work is published in, not what it is (config/source-types.yaml minus "other").
SOURCE_TYPES = {"journal", "repository", "conference", "ebook platform", "book series"}

# The entity prefixes TermField strips from a `type` value (core/fields.py _normalize_term_value),
# so a value is read here exactly as the query reads it.
_ENTITY_PREFIXES = ("work-types/", "institution-types/", "source-types/", "types/")


@lru_cache(maxsize=1)
def work_types():
    """The work types, sorted (config/work-types.yaml via the entity registry, fixed per process)."""
    from core.entities import get_entity_type

    ent = get_entity_type("work-types")
    if not ent:
        return ()
    return tuple(sorted(str(row["id"]).split("/", 1)[-1] for row in ent.values or []))


def _normalize(value):
    return TermField._strip_openalex_prefix(value, *_ENTITY_PREFIXES).lower()


def _did_you_mean(code, types):
    guess = code.replace("_", "-").replace(" ", "-")
    for cand in (guess, guess.rstrip("s")):
        if cand in types:
            return cand
    close = difflib.get_close_matches(guess, types, n=1, cutoff=0.8)  # 0.8 as validator._SUGGEST_CUTOFF
    return close[0] if close else None


def suggested_type(value, types=None):
    """The work type someone who typed `value` most likely wants, or None. OQL's invalid_value
    message uses it for its "Did you mean" fix-it."""
    types = types if types is not None else work_types()
    code = _normalize(value)
    if code in types:
        return code
    if code in RETIRED:
        return RETIRED[code].use
    if code in SOURCE_LABELS:
        return SOURCE_LABELS[code]
    if code in SOURCE_TYPES:
        return None
    return _did_you_mean(code, types)


def retired_without_replacement(value):
    """For a retired type no other type took over (grant, libguides): the sentence that says when it
    left and why; else None. OQL's invalid_value message adds it where it has no "Did you mean"."""
    code = _normalize(value)
    retired = RETIRED.get(code)
    if not retired or retired.use:
        return None
    return f"'{code}' is no longer a work type (removed {retired.removed}): {retired.why}"


def unknown_type_message(value, types=None):
    """None when `value` names a work type (or is null); else the sentence that says why not and what to use."""
    types = types if types is not None else work_types()
    code = _normalize(value)
    if not types or code in types or code == "null":
        return None
    use = suggested_type(code, types)
    if code in RETIRED:
        if use:
            hint = (f"'{code}' is no longer a work type (removed {RETIRED[code].removed}); most of those works "
                    f"are now typed {use}. Use type:{use}.")
        else:
            hint = retired_without_replacement(code)
    elif code in SOURCE_TYPES:
        hint = (f"'{code}' is a source type, not a work type. To filter works by where they were published, "
                f"use primary_location.source.type:{code}.")
    elif code in SOURCE_LABELS:
        hint = (f"'{code}' is a source's own label (Crossref's), not an OpenAlex work type; most works with "
                f"that label are typed {use}. Use type:{use}, or primary_location.raw_type:{code} to filter "
                f"on the label itself.")
    else:
        hint = f"'{code}' is not a work type." + (f" Did you mean type:{use}?" if use else "")
    return f"{hint} The work types are: {', '.join(types)} (https://api.openalex.org/types)."


def _operands(value, is_quoted):
    """The values a filter value names, split as core.filter routes it (| = OR, space = AND unless
    quoted), each without its leading `!`."""
    if "|" in value:
        parts = value.split("|")
    elif " " in value and not is_quoted:
        parts = value.split(" ")
    else:
        parts = [value]
    return [p[1:] if p.startswith("!") else p for p in parts]


def check_work_type_filter(field, value, is_quoted=False):
    """Raise APIQueryParamsError (a JSON 400) when a works `type` filter names something that isn't
    a work type. `value` is the filter value after quote handling, as core.filter routes it."""
    if not isinstance(field, TermField) or field.entity_type != "work-types":
        return
    types = work_types()
    for operand in _operands(value, is_quoted):
        message = operand and unknown_type_message(operand, types)
        if message:
            raise APIQueryParamsError(message)
