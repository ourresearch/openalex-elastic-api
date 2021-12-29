from marshmallow import INCLUDE, Schema, fields


class MetaSchema(Schema):
    count = fields.Int()
    db_response_time_ms = fields.Int()
    page = fields.Int()
    per_page = fields.Int()

    class Meta:
        ordered = True


class GroupBySchema(Schema):
    key = fields.Str()
    count = fields.Int(attribute="doc_count")

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
