from marshmallow import INCLUDE, Schema, fields

from core.schemas import GroupBySchema, MetaSchema


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


class HostVenueSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    publisher = fields.Str()
    issn = fields.List(fields.Str())
    issn_l = fields.Str()
    type = fields.Str()
    url = fields.Str()
    is_oa = fields.Bool()
    version = fields.Str()
    license = fields.Str()

    class Meta:
        ordered = True


class AlternateHostVenuesSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    is_best = fields.Str()
    is_oa = fields.Bool()
    license = fields.Str()
    url = fields.Str()
    version = fields.Str()

    class Meta:
        ordered = True


class OpenAccessSchema(Schema):
    is_oa = fields.Bool()
    oa_status = fields.Str()
    oa_url = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class IDsSchema(Schema):
    doi = fields.Str()
    mag = fields.Str()
    openalex = fields.Str()
    pmid = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class WorksSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    publication_date = fields.Str()
    relevance_score = fields.Float(attribute="meta.score")
    host_venue = fields.Nested(HostVenueSchema)
    authorships = fields.Nested(AuthorshipsSchema, many=True)
    concepts = fields.Nested(ConceptsSchema, many=True)
    alternate_host_venues = fields.List(fields.Nested(AlternateHostVenuesSchema))
    open_access = fields.Nested(OpenAccessSchema)
    cited_by_count = fields.Int()
    ids = fields.Nested(IDsSchema)
    publication_year = fields.Int()
    cited_by_api_url = fields.List(fields.Str())
    doi = fields.Str()
    type = fields.Str()
    is_paratext = fields.Bool()
    is_retracted = fields.Bool()
    references_count = fields.Int()
    referenced_works = fields.List(fields.Str())
    related_works = fields.List(fields.Str())
    url = fields.Str()
    biblio = fields.Function(
        lambda obj: obj.biblio.to_dict() if "biblio" in obj and obj.biblio else None
    )
    abstract_inverted_index = fields.Function(
        lambda obj: obj.abstract_inverted_index.to_dict()
        if "abstract_inverted_index" in obj and obj.abstract_inverted_index
        else None
    )

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(WorksSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
