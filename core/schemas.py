from marshmallow import Schema, fields


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
