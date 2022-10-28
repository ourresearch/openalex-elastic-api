from marshmallow import Schema, fields

from core.schemas import MetaSchema


class SuggestSchema(Schema):
    phrase = fields.Str()
    count = fields.Int()


class SuggestMessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(SuggestSchema, many=True)

    class Meta:
        ordered = True
