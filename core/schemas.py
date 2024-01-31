from marshmallow import INCLUDE, Schema, fields


class MetaSchema(Schema):
    count = fields.Int()
    q = fields.Str()
    db_response_time_ms = fields.Int()
    page = fields.Int()
    per_page = fields.Int()
    next_cursor = fields.Str()
    groups_count = fields.Int()

    class Meta:
        ordered = True


class GroupBySchema(Schema):
    key = fields.Str()
    key_display_name = fields.Str()
    count = fields.Int(attribute="doc_count")

    class Meta:
        ordered = True


class GroupBysSchema(Schema):
    group_by_key = fields.Str()
    groups = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True


class HistogramSchema(Schema):
    min = fields.Integer()
    key = fields.Integer()
    max = fields.Integer()
    count = fields.Int(attribute="doc_count")

    class Meta:
        ordered = True


class HistogramWrapperSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(HistogramSchema, many=True)

    class Meta:
        ordered = True


class CountsByYearSchema(Schema):
    year = fields.Int()
    works_count = fields.Int()
    cited_by_count = fields.Int()

    class Meta:
        ordered = True
        unknown = INCLUDE


class XConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Float()

    class Meta:
        ordered = True


class SummaryStatsSchema(Schema):
    two_year_mean_citedness = fields.Float(
        attribute="2yr_mean_citedness", data_key="2yr_mean_citedness"
    )
    h_index = fields.Int()
    i10_index = fields.Int()

    class Meta:
        ordered = True


class ValuesSchema(Schema):
    value = fields.Str()
    display_name = fields.Str()
    count = fields.Int()
    url = fields.Str()
    db_response_time_ms = fields.Int()

    class Meta:
        ordered = True


class FilterSchema(Schema):
    key = fields.Str()
    is_negated = fields.Boolean()
    type = fields.Str()
    values = fields.List(fields.Nested(ValuesSchema))

    class Meta:
        ordered = True


class FiltersWrapperSchema(Schema):
    filters = fields.Nested(FilterSchema, many=True)

    class Meta:
        ordered = True


class NumberIdSchema(Schema):
    id = fields.Integer()
    display_name = fields.Str()

    class Meta:
        ordered = True


class RolesSchema(Schema):
    role = fields.Str()
    id = fields.Str()
    works_count = fields.Int()

    class Meta:
        ordered = True


class PercentilesSchema(Schema):
    percentile = fields.Float()
    value = fields.Float()

    class Meta:
        ordered = True


class StatsMetaSchema(Schema):
    count = fields.Int()
    entity = fields.Str()
    filters = fields.List(fields.Dict())
    search = fields.Str()
    db_response_time_ms = fields.Int()

    class Meta:
        ordered = True


class StatsSchema(Schema):
    key = fields.Str()
    percentiles = fields.Dict(keys=fields.Integer(), values=fields.Integer())
    sum = fields.Integer()

    class Meta:
        ordered = True


class StatsWrapperSchema(Schema):
    meta = fields.Nested(StatsMetaSchema)
    stats = fields.Nested(StatsSchema, many=True)

    class Meta:
        ordered = True


def hide_relevance(data, context):
    if "relevance_score" in data.keys() and (
        not data["relevance_score"]
        and data["relevance_score"] != 0
        or "display_relevance" in context
        and context["display_relevance"] is False
    ):
        del data["relevance_score"]
    return data


def relevance_score(obj):
    if obj.meta.score and obj.meta != 0.0:
        return obj.meta.score
