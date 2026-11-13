from marshmallow import INCLUDE, Schema, fields, post_dump
from marshmallow.utils import get_value

from core.schemas import (CountsByYearSchema, DoiUrl, GroupBySchema, GroupBysSchema,
                          MetaSchema, RolesSchema, RoundedSummaryStatsSchema,
                          hide_relevance, relevance_score)
from core.utils import normalize_openalex_id


class IDsSchema(Schema):
    openalex = fields.Str()
    ror = fields.Str()
    wikidata = fields.Str()
    crossref = fields.Str()
    doi = DoiUrl()

    class Meta:
        ordered = True
        unknown = INCLUDE


class FundersSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    alternate_titles = fields.List(fields.Str())
    country_code = fields.Str(dump_default=None)
    description = fields.Str(dump_default=None)
    homepage_url = fields.Str(dump_default=None)
    image_url = fields.Str(dump_default=None)
    image_thumbnail_url = fields.Str(dump_default=None)
    relevance_score = fields.Method("get_relevance_score")
    awards_count = fields.Int()
    works_count = fields.Int()
    cited_by_count = fields.Int()
    summary_stats = fields.Nested(RoundedSummaryStatsSchema, dump_default=None)
    ids = fields.Nested(IDsSchema)
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    roles = fields.List(fields.Nested(RolesSchema))
    # The queries that list what works_count and awards_count count, as authors and institutions serve them (Casey 11-12).
    # Built here from the id: the funders index stores neither, so nothing is re-sent.
    works_api_url = fields.Method("get_works_api_url")
    awards_api_url = fields.Method("get_awards_api_url")
    updated_date = fields.Str()
    created_date = fields.Str(dump_default=None)

    @staticmethod
    def _api_url(obj, entity, filter_key):
        short_id = normalize_openalex_id(get_value(obj, "id", default=None))
        return f"https://api.openalex.org/{entity}?filter={filter_key}:{short_id}" if short_id else None

    def get_works_api_url(self, obj):
        return self._api_url(obj, "works", "funders.id")

    def get_awards_api_url(self, obj):
        return self._api_url(obj, "awards", "funder.id")

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(FundersSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)
    group_bys = fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
