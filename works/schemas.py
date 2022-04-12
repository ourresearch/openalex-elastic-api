import json

from marshmallow import INCLUDE, Schema, fields, post_dump

from core.schemas import CountsByYearSchema, GroupBySchema, MetaSchema


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
    author_position = fields.Str()
    author = fields.Nested(AuthorSchema)
    institutions = fields.Nested(InstitutionsSchema, many=True)
    raw_affiliation_string = fields.Str()

    class Meta:
        ordered = True


class ConceptsSchema(Schema):
    id = fields.Str()
    wikidata = fields.Str()
    display_name = fields.Str()
    level = fields.Int()
    score = fields.Decimal()

    class Meta:
        ordered = True


class HostVenueSchema(Schema):
    id = fields.Str()
    issn_l = fields.Str()
    issn = fields.List(fields.Str())
    display_name = fields.Str()
    publisher = fields.Str()
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
    type = fields.Str()
    url = fields.Str()
    is_oa = fields.Bool()
    is_best = fields.Str()
    version = fields.Str()
    license = fields.Str()

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
    openalex = fields.Str()
    doi = fields.Str()
    mag = fields.Str()
    pmid = fields.Str()
    pmcid = fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class MeshSchema(Schema):
    descriptor_ui = fields.Str()
    descriptor_name = fields.Str()
    qualifier_ui = fields.Str()
    qualifier_name = fields.Str()
    is_major_topic = fields.Boolean()

    class Meta:
        ordered = True


class WorksSchema(Schema):
    id = fields.Str()
    doi = fields.Str()
    title = fields.Str()
    display_name = fields.Str()
    relevance_score = fields.Method("get_relevance_score")
    publication_year = fields.Int()
    publication_date = fields.Str()
    ids = fields.Nested(IDsSchema)
    host_venue = fields.Nested(HostVenueSchema)
    type = fields.Str()
    open_access = fields.Nested(OpenAccessSchema)
    authorships = fields.Nested(AuthorshipsSchema, many=True)
    cited_by_count = fields.Int()
    biblio = fields.Function(
        lambda obj: obj.biblio.to_dict() if "biblio" in obj and obj.biblio else None
    )
    is_retracted = fields.Bool()
    is_paratext = fields.Bool()
    concepts = fields.Nested(ConceptsSchema, many=True)
    mesh = fields.List(fields.Nested(MeshSchema))
    alternate_host_venues = fields.List(fields.Nested(AlternateHostVenuesSchema))
    referenced_works = fields.List(fields.Str())
    related_works = fields.List(fields.Str())
    abstract_inverted_index = fields.Function(
        lambda obj: json.loads(obj.abstract_inverted_index).get("InvertedIndex")
        if "abstract_inverted_index" in obj and obj.abstract_inverted_index
        else None
    )
    cited_by_api_url = fields.Str()
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    updated_date = fields.Str()
    created_date = fields.Str(default=None)

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        if (
            not data["relevance_score"]
            and data["relevance_score"] != 0
            or "display_relevance" in self.context
            and self.context["display_relevance"] is False
        ):
            del data["relevance_score"]
        return data

    def get_relevance_score(self, obj):
        return obj.meta.score

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(WorksSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
