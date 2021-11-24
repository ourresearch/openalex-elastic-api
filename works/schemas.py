from marshmallow import INCLUDE, Schema, fields, validate
from marshmallow.validate import OneOf


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


class WorksQuerySchema(Schema):
    filter_old = fields.List(
        fields.Dict(keys=fields.Str, values=fields.Str),
        description="List of filters in format filter=year:2020,issn:9982-2342",
        validate=validate.Length(min=2, max=40),
        required=False,
    )
    search = fields.List(
        fields.Dict(keys=fields.Str, values=fields.Str),
        description="List of search options in format search=author_name:greg jones",
        validate=validate.Length(min=2, max=40),
        required=False,
    )
    details = fields.Bool(description="Display detailed records. Default is 10.")
    sort = fields.Str(validate=OneOf(["asc", "desc"]))
    page = fields.Int()

    class Meta:
        ordered = True
