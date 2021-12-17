from marshmallow import INCLUDE, Schema, fields


class MetaSchema(Schema):
    count = fields.Int()
    response_time = fields.Str()
    page = fields.Int()
    per_page = fields.Int()

    class Meta:
        ordered = True


class AuthorSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    orcid = fields.Str()

    class Meta:
        ordered = True


class InstitutionsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    ror = fields.Str()
    country_code = fields.Str()
    type = fields.Str()

    class Meta:
        ordered = True


class AuthorshipsSchema(Schema):
    author = fields.Nested(AuthorSchema)
    institutions = fields.Nested(InstitutionsSchema, many=True)
    author_position = fields.Str()

    class Meta:
        ordered = True


class ConceptsSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    score = fields.Decimal()
    level = fields.Int()
    wikidata = fields.Str()

    class Meta:
        ordered = True


class VenueSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    publisher = fields.Str()
    issn = fields.List(fields.Str())
    issn_l = fields.Str()

    class Meta:
        ordered = True


class AlternateLocationsSchema(Schema):
    is_best = fields.Str()
    is_oa = fields.Bool()
    license = fields.Str()
    url = fields.Str()
    venue_id = fields.Str()
    version = fields.Str()


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
    doi = fields.Str()
    pmid = fields.Str()
    openalex = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class WorksSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    publication_date = fields.Str()
    venue = fields.Nested(VenueSchema)
    authorships = fields.Nested(AuthorshipsSchema, many=True)
    concepts = fields.Nested(ConceptsSchema, many=True)
    alternate_locations = fields.Nested(AlternateLocationsSchema)
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    publication_year = fields.Int()
    cited_by_api_url = fields.List(fields.Str())
    doi = fields.Str()
    genre = fields.Str()
    is_oa = fields.Bool()
    is_paratext = fields.Bool()
    oa_status = fields.Str()
    oa_url = fields.Str()
    references_count = fields.Int()
    related_works = fields.List(fields.Str())
    url = fields.Str()
    bibio = fields.Function(lambda obj: obj.bibio.to_dict())
    abstract_inverted_index = fields.Function(
        lambda obj: obj.abstract_inverted_index.to_dict()
        if obj.abstract_inverted_index
        else None
    )

    class Meta:
        ordered = True


class GroupBySchema(Schema):
    key = fields.Str()
    count = fields.Int(attribute="doc_count")

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(WorksSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
