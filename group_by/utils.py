from elasticsearch import NotFoundError
from elasticsearch_dsl import Search

from settings import GROUPBY_VALUES_INDEX


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
