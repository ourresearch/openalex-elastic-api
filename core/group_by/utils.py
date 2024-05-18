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


def get_all_groupby_values(entity, field):
    # temp fix for best_oa_location.license
    if field == "best_oa_location.license":
        field = "locations.license"

    s = Search(index=GROUPBY_VALUES_INDEX)
    s = s.filter("term", entity=entity)
    s = s.filter("term", group_by=field)
    try:
        response = s.execute()
        buckets = response[0].buckets
        return buckets if buckets else []
    except (NotFoundError, IndexError):
        # Nothing found for this entity/groupby combination
        return []
