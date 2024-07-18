from marshmallow import Schema, fields, post_dump


class QueryStringSchema(Schema):
    original = fields.Str()
    oql = fields.Str()
    v1 = fields.Str()

    class Meta:
        ordered = True


class AutoCompleteSchema(Schema):
    type = fields.Str()
    suggestions = fields.List(fields.Str())

    class Meta:
        ordered = True


class QuerySchema(Schema):
    query = fields.Nested(QueryStringSchema)
    is_valid = fields.Bool()
    autocomplete = fields.Nested(AutoCompleteSchema)

    class Meta:
        ordered = True


class BadQuerySchema(Schema):
    offset = fields.Int()
    description = fields.Str()
    suggestion = fields.Str()

    class Meta:
        ordered = True
