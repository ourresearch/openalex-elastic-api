from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, Search, connections

import settings


def alter_records():
    es = Elasticsearch([settings.ES_URL], timeout=30)
    s = Search(index=settings.WORKS_INDEX)
    s = s.extra(size=10000)
    s = s.filter(
        Q("exists", field="locations.source.host_organization_lineage")
        | Q("exists", field="primary_location.source.host_organization_lineage")
        | Q("exists", field="best_oa_location.source.host_organization_lineage")
        | Q("exists", field="host_venue.host_organization_lineage")
        | Q("exists", field="alternate_host_venues.host_organization_lineage")
    )
    print(f"Remaining: {s.count()}")
    response = s.execute()
    count = 0
    for r in response:
        count = count + 1
        location_count = 0
        venue_count = 0
        for location in r.locations:
            if location.source and "host_organization_lineage" in location.source:
                r.locations[location_count].source.host_organization_lineage = None
            location_count = location_count + 1
        if (
            r.primary_location
            and "source" in r.primary_location
            and r.primary_location.source
            and "host_organization_lineage" in r.primary_location.source
        ):
            r.primary_location.source.host_organization_lineage = None
        if (
            r.best_oa_location
            and "source" in r.best_oa_location
            and r.best_oa_location.source
            and "host_organization_lineage" in r.best_oa_location.source
        ):
            r.best_oa_location.source.host_organization_lineage = None
        if r.host_venue and "host_organization_lineage" in r.host_venue:
            r.host_venue.host_organization_lineage = None
        for venue in r.alternate_host_venues:
            if "host_organization_lineage" in venue:
                r.alternate_host_venues[venue_count].host_organization_lineage = None
            venue_count = venue_count + 1

        doc = r.to_dict()
        if "@version" in doc:
            del doc["@version"]
        # index the record to replace the existing one
        es.index(index=r.meta.index, id=r.id, document=doc)
        # refresh the index
        print(f"Updated: {r.id}")
    es.indices.refresh(index=settings.WORKS_INDEX)
    print(f"count: {count}")


if __name__ == "__main__":
    connections.create_connection(hosts=[settings.ES_URL], timeout=30)
    alter_records()
