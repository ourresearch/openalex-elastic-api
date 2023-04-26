from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          SummaryStatsSchema, XConceptsSchema, hide_relevance,
                          relevance_score)


class IDsSchema(Schema):
    openalex = fields.Str()
    ror = fields.Str()
    mag = fields.Str()
    grid = fields.Str()
    wikipedia = fields.Str()
    wikidata = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class GeoSchema(Schema):
    city = fields.Str()
    geonames_city_id = fields.Str()
    region = fields.Str()
    country_code = fields.Str()
    country = fields.Str()
    latitude = fields.Float()
    longitude = fields.Float()

    class Meta:
        ordered = True
        unknown = INCLUDE


class AssociatedInstitutionsSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    country_code = fields.Str()
    type = fields.Str()
    relationship = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class RepositoriesSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    host_organization = fields.Str()
    host_organization_name = fields.Str()
    host_organization_lineage = fields.List(fields.Str())

    class Meta:
        ordered = True


class InstitutionsSchema(Schema):
    id = fields.Str()
    ror = fields.Str()
    display_name = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    country_code = fields.Str()
    type = fields.Str()
    homepage_url = fields.Str()
    image_url = fields.Str()
    image_thumbnail_url = fields.Str()
    display_name_acronyms = fields.List(fields.Str())
    display_name_alternatives = fields.List(fields.Str())
    repositories = fields.List(fields.Nested(RepositoriesSchema))
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(SummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    geo = fields.Nested(GeoSchema)
    international = fields.Method("get_international")
    associated_institutions = fields.List(fields.Nested(AssociatedInstitutionsSchema))
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    x_concepts = fields.List(fields.Nested(XConceptsSchema))
    works_api_url = fields.Str()
    updated_date = fields.Str()
    created_date = fields.Str(dump_default=None)

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    def get_international(self, obj):
        sorted_dict = {}
        if obj and "international" in obj:
            international = obj.international.to_dict()
            display_names = international.get("display_name")
            sorted_dict["display_name"] = (
                dict(sorted(display_names.items())) if display_names else None
            )
        return sorted_dict

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(InstitutionsSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
