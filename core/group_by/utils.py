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
    known = False
    if ":" in group_by:
        group_by_split = group_by.split(":")
        if len(group_by_split) == 2 and group_by_split[1].lower() == "known":
            group_by = group_by_split[0]
            known = True
        elif len(group_by_split) == 2 and group_by_split[1].lower() != "known":
            raise APIQueryParamsError(
                "The only valid filter for a group_by param is 'known', which hides the unknown group from results."
            )
    return group_by, known


def get_all_groupby_values(entity, field):
    s = Search(index=GROUPBY_VALUES_INDEX)
    s = s.filter("term", entity=entity)
    s = s.filter("term", group_by=field)
    try:
        response = s.execute()
        return response[0].buckets
    except (NotFoundError, IndexError):
        # Nothing found for this entity/groupby combination
        return []
