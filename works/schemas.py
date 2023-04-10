import json

from marshmallow import INCLUDE, Schema, fields, post_dump, pre_dump

from core.schemas import (CountsByYearSchema, GroupBySchema, MetaSchema,
                          hide_relevance, relevance_score)


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
    is_corresponding = fields.Bool()
    raw_affiliation_string = fields.Str()

    class Meta:
        ordered = True


class BiblioSchema(Schema):
    volume = fields.Str()
    issue = fields.Str()
    first_page = fields.Str()
    last_page = fields.Str()

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


class SourceSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    issn_l = fields.Str()
    issn = fields.List(fields.Str())
    host_organization = fields.Str()
    host_organization_name = fields.Str()
    type = fields.Str()

    class Meta:
        ordered = True


class LocationSchema(Schema):
    is_oa = fields.Bool()
    landing_page_url = fields.Str()
    pdf_url = fields.Str()
    source = fields.Nested(SourceSchema)
    venue = fields.Nested(SourceSchema)
    license = fields.Str()
    version = fields.Str()

    class Meta:
        ordered = True


class OpenAccessSchema(Schema):
    is_oa = fields.Bool()
    oa_status = fields.Str()
    oa_url = fields.Str()
    any_repository_has_fulltext = fields.Bool()

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
    primary_location = fields.Nested(LocationSchema)
    host_venue = fields.Nested(HostVenueSchema)
    type = fields.Str()
    open_access = fields.Nested(OpenAccessSchema)
    authorships = fields.Nested(AuthorshipsSchema, many=True)
    is_authors_truncated = fields.Bool(attribute="authorships_truncated")
    cited_by_count = fields.Int()
    biblio = fields.Nested(BiblioSchema)
    is_retracted = fields.Bool()
    is_paratext = fields.Bool()
    concepts = fields.Nested(ConceptsSchema, many=True)
    mesh = fields.List(fields.Nested(MeshSchema))
    locations = fields.Nested(LocationSchema, many=True)
    best_oa_location = fields.Nested(LocationSchema)
    alternate_host_venues = fields.List(fields.Nested(AlternateHostVenuesSchema))
    referenced_works = fields.List(fields.Str())
    related_works = fields.List(fields.Str())
    ngrams_url = fields.Method("get_ngrams_url")
    abstract_inverted_index = fields.Function(
        lambda obj: json.loads(obj.abstract_inverted_index).get("InvertedIndex")
        if "abstract_inverted_index" in obj and obj.abstract_inverted_index
        else None
    )
    cited_by_api_url = fields.Str()
    counts_by_year = fields.List(fields.Nested(CountsByYearSchema))
    updated_date = fields.Str()
    created_date = fields.Str(dump_default=None)

    @pre_dump
    def pre_dump(self, data, **kwargs):
        """If single record, display authorships_full rather than truncated list."""
        if "single_record" in self.context and self.context["single_record"]:
            if "authorships_full" in data:
                data.authorships = data.authorships_full
                del data.authorships_truncated
        return data

    @post_dump
    def remove_relevance_score(self, data, many, **kwargs):
        return hide_relevance(data, self.context)

    @staticmethod
    def get_relevance_score(obj):
        return relevance_score(obj)

    @staticmethod
    def get_ngrams_url(obj):
        short_id = obj.id.replace("https://openalex.org/", "")
        ngrams_url = f"https://api.openalex.org/works/{short_id}/ngrams"
        return ngrams_url

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(WorksSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
