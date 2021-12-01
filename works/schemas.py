from marshmallow import INCLUDE, Schema, fields
from marshmallow.validate import OneOf


class MetaSchema(Schema):
    count = fields.Int()
    response_time = fields.Str()
    page = fields.Int()
    per_page = fields.Int()
    query = fields.Dict()

    class Meta:
        ordered = True


class AffiliationsSchema(Schema):
    author_display_name = fields.Str()
    institution_display_name = fields.Str()
    city = fields.Str()
    country = fields.Str()
    country_code = fields.Str()
    author_sequence_number = fields.Int()
    author_id = fields.Int()
    ror = fields.List(fields.Str())
    institution_id = fields.Int()
    grid_id = fields.Str()
    orcid = fields.List(fields.Str())

    class Meta:
        ordered = True


class ConceptsSchema(Schema):
    name = fields.Str(attribute="display_name")
    field_of_study_id = fields.Int()
    score = fields.Decimal()

    class Meta:
        ordered = True


class JournalSchema(Schema):
    title = fields.Str()
    publisher = fields.Str()
    issns = fields.Str(attribute="all_issns")
    journal_id = fields.Int()

    class Meta:
        ordered = True


class UnpaywallSchema(Schema):
    oa_status = fields.Str()
    is_oa_bool = fields.Bool()
    journal_is_oa = fields.Bool()
    has_green = fields.Bool()
    best_license = fields.Str()
    best_url = fields.Str()
    best_host_type = fields.Str()
    best_version = fields.Str()
    genre = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class IDsSchema(Schema):
    doi = fields.List(fields.Str)
    pmid = fields.List(fields.Str)

    class Meta:
        ordered = True
        unknown = INCLUDE


class WorksSchema(Schema):
    id = fields.Int(attribute="paper_id")
    work_title = fields.Str()
    publication_date = fields.Str()
    journal = fields.Nested(JournalSchema)
    affiliations = fields.Nested(AffiliationsSchema, many=True)
    concepts = fields.Nested(ConceptsSchema, many=True)
    unpaywall = fields.Nested(UnpaywallSchema)
    ids = fields.Nested(IDsSchema)
    locations = fields.List(fields.List(fields.Str()))
    citation_count = fields.Int()
    issue = fields.Str()
    volume = fields.Str()
    first_page = fields.Str()
    last_page = fields.Str()
    doc_type = fields.Str()
    year = fields.Int()

    class Meta:
        ordered = True


class GroupBySchema(Schema):
    key = fields.Str()
    count = fields.Int(attribute="doc_count")

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    details = fields.Nested(WorksSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True


class WorksQuerySchema(Schema):
    group_by = fields.Str(
        validate=OneOf(["author_id", "country", "issn", "open_access", "year"]),
        description="Group by a field.",
    )
    details = fields.Bool(
        description="Display detailed list of works. Default number of records returned is 10."
    )
    page = fields.Int(missing=1)
    per_page = fields.Int(missing=10)
    group_by_size = fields.Int(missing=50)

    class Meta:
        ordered = True
