from elasticsearch import NotFoundError
from elasticsearch_dsl import Search

from core.exceptions import APIQueryParamsError
from settings import GROUPBY_VALUES_INDEX


def get_bucket_keys(group_by):
    return {
        "default": format_key("groupby", group_by),
        "exists": format_key("exists", group_by),
        "not_exists": format_key("not_exists", group_by),
    }


def format_key(base, group_by):
    return f"{base}_{group_by.replace('.', '_')}"


def is_multi_dim_group_by(group_by_string):
    """A comma in the (singular) `group_by` param means multi-dimensional,
    NESTED grouping (cross-product) — distinct from `group_bys` (plural), which
    is independent side-by-side facets. See oxjob #387."""
    return bool(group_by_string) and "," in group_by_string


def parse_group_by_dimensions(group_by_string):
    """Split a multi-dim `group_by=a,b[,c]` string into an ordered list of
    (field, include_unknown) tuples — one per nesting level, outermost first.
    A single-dim string yields a one-element list."""
    return [parse_group_by(part) for part in group_by_string.split(",")]


def parse_group_by(group_by):
    include_unknown = False
    if ":" in group_by:
        group_by_split = group_by.split(":")
        if len(group_by_split) == 2 and group_by_split[1].lower() == "include_unknown":
            group_by = group_by_split[0]
            include_unknown = True
        elif len(group_by_split) == 2 and group_by_split[1].lower() == "known":
            group_by = group_by_split[0]
            include_unknown = False
        elif len(group_by_split) == 2:
            raise APIQueryParamsError(
                "The only valid filters for a group_by param is 'include_unknown' or the deprecated value 'known'"
            )

    return group_by, include_unknown


def get_all_groupby_values(entity, field, connection='default'):
    # temp fix for best_oa_location.license
    if field == "best_oa_location.license":
        field = "locations.license"

    s = Search(index=GROUPBY_VALUES_INDEX, using=connection)
    s = s.filter("term", entity=entity)
    s = s.filter("term", group_by=field)
    try:
        response = s.execute()
        buckets = response[0].buckets
        return buckets if buckets else []
    except (NotFoundError, IndexError):
        # Nothing found for this entity/groupby combination
        return []
