import json

from marshmallow import INCLUDE, Schema, post_dump, pre_dump
from marshmallow import (
    fields as ma_fields,
)  # imported as ma_fields due to conflict with "fields" in WorkSchema

from core.schemas import (
    CountsByYearSchema,
    GroupBySchema,
    GroupBysSchema,
    MetaSchema,
    NumberIdSchema,
    hide_relevance,
    relevance_score,
)


class AuthorSchema(Schema):
    id = ma_fields.Str()
    display_name = ma_fields.Str()
    orcid = ma_fields.Str()

    class Meta:
        ordered = True


class InstitutionsSchema(Schema):
    id = ma_fields.Str()
    display_name = ma_fields.Str()
    ror = ma_fields.Str()
    country_code = ma_fields.Str()
    type = ma_fields.Str()
    lineage = ma_fields.List(ma_fields.Str())

    class Meta:
        ordered = True


class AuthorshipsSchema(Schema):
    author_position = ma_fields.Str()
    author = ma_fields.Nested(AuthorSchema)
    institutions = ma_fields.Nested(InstitutionsSchema, many=True)
    countries = ma_fields.List(ma_fields.Str())
    is_corresponding = ma_fields.Bool()
    raw_author_name = ma_fields.Str()
    raw_affiliation_string = ma_fields.Str()
    raw_affiliation_strings = ma_fields.List(ma_fields.Str())

    class Meta:
        ordered = True


class BiblioSchema(Schema):
    volume = ma_fields.Str()
    issue = ma_fields.Str()
    first_page = ma_fields.Str()
    last_page = ma_fields.Str()

    class Meta:
        ordered = True


class ConceptsSchema(Schema):
    id = ma_fields.Str()
    wikidata = ma_fields.Str()
    display_name = ma_fields.Str()
    level = ma_fields.Int()
    score = ma_fields.Float()

    class Meta:
        ordered = True


class GrantsSchema(Schema):
    funder = ma_fields.Str()
    funder_display_name = ma_fields.Str()
    award_id = ma_fields.Str()

    class Meta:
        ordered = True


class SourceSchema(Schema):
    id = ma_fields.Str()
    display_name = ma_fields.Str()
    issn_l = ma_fields.Str()
    issn = ma_fields.List(ma_fields.Str())
    is_oa = ma_fields.Bool()
    is_in_doaj = ma_fields.Bool()
    host_organization = ma_fields.Str()
    host_organization_name = ma_fields.Str()
    host_organization_lineage = ma_fields.List(ma_fields.Str())
    host_organization_lineage_names = ma_fields.List(ma_fields.Str())
    type = ma_fields.Str()

    class Meta:
        ordered = True


class LocationSchema(Schema):
    is_oa = ma_fields.Bool()
    landing_page_url = ma_fields.Str()
    pdf_url = ma_fields.Str()
    source = ma_fields.Nested(SourceSchema)
    license = ma_fields.Str()
    version = ma_fields.Str()
    is_accepted = ma_fields.Bool()
    is_published = ma_fields.Bool()

    class Meta:
        ordered = True


class OpenAccessSchema(Schema):
    is_oa = ma_fields.Bool()
    oa_status = ma_fields.Str()
    oa_url = ma_fields.Str()
    any_repository_has_fulltext = ma_fields.Bool()

    class Meta:
        ordered = True
        unknown = INCLUDE


class IDsSchema(Schema):
    openalex = ma_fields.Str()
    doi = ma_fields.Str()
    mag = ma_fields.Str()
    pmid = ma_fields.Str()
    pmcid = ma_fields.Str()

    class Meta:
        ordered = True
        unknown = INCLUDE


class MeshSchema(Schema):
    descriptor_ui = ma_fields.Str()
    descriptor_name = ma_fields.Str()
    qualifier_ui = ma_fields.Str()
    qualifier_name = ma_fields.Str()
    is_major_topic = ma_fields.Boolean()

    class Meta:
        ordered = True


class APCSchema(Schema):
    value = ma_fields.Integer()
    currency = ma_fields.Str()
    value_usd = ma_fields.Integer()
    provenance = ma_fields.Str()

    class Meta:
        ordered = True


class SDGSchema(Schema):
    id = ma_fields.String()
    display_name = ma_fields.String()
    score = ma_fields.Float()


class TopicSchema(Schema):
    id = ma_fields.Str()
    display_name = ma_fields.Str()
    score = ma_fields.Float()
    subfield = ma_fields.Nested(NumberIdSchema)
    field = ma_fields.Nested(NumberIdSchema)
    domain = ma_fields.Nested(NumberIdSchema)

    class Meta:
        ordered = True


class CitedByPercentileYearSchema(Schema):
    min = ma_fields.Integer()
    max = ma_fields.Integer()

    class Meta:
        ordered = True


class KeywordsSchema(Schema):
    keyword = ma_fields.String()
    score = ma_fields.Float()

    class Meta:
        ordered = True


class WorksSchema(Schema):
    id = ma_fields.Str()
    doi = ma_fields.Str()
    title = ma_fields.Str()
    display_name = ma_fields.Str()
    relevance_score = ma_fields.Method("get_relevance_score")
    publication_year = ma_fields.Int()
    publication_date = ma_fields.Str()
    ids = ma_fields.Nested(IDsSchema)
    language = ma_fields.Str()
    primary_location = ma_fields.Nested(LocationSchema)
    type = ma_fields.Str()
    type_crossref = ma_fields.Str()
    indexed_in = ma_fields.List(ma_fields.Str())
    open_access = ma_fields.Nested(OpenAccessSchema)
    authorships = ma_fields.Nested(AuthorshipsSchema, many=True)
    countries_distinct_count = ma_fields.Int()
    institutions_distinct_count = ma_fields.Int()
    corresponding_author_ids = ma_fields.List(ma_fields.Str())
    corresponding_institution_ids = ma_fields.List(ma_fields.Str())
    apc_list = ma_fields.Nested(APCSchema, dump_default=None)
    apc_paid = ma_fields.Nested(APCSchema, dump_default=None)
    is_authors_truncated = ma_fields.Bool(attribute="authorships_truncated")
    has_fulltext = ma_fields.Bool()
    fulltext_origin = ma_fields.Str()
    cited_by_count = ma_fields.Int()
    cited_by_percentile_year = ma_fields.Nested(CitedByPercentileYearSchema)
    biblio = ma_fields.Nested(BiblioSchema)
    is_retracted = ma_fields.Bool()
    is_paratext = ma_fields.Bool()
    primary_topic = ma_fields.Nested(TopicSchema)
    topics = ma_fields.Nested(TopicSchema, many=True)
    keywords = ma_fields.Nested(KeywordsSchema, many=True)
    concepts = ma_fields.Nested(ConceptsSchema, many=True)
    mesh = ma_fields.List(ma_fields.Nested(MeshSchema))
    locations_count = ma_fields.Int()
    locations = ma_fields.Nested(LocationSchema, many=True)
    best_oa_location = ma_fields.Nested(LocationSchema)
    sustainable_development_goals = ma_fields.Nested(SDGSchema, many=True)
    grants = ma_fields.List(ma_fields.Nested(GrantsSchema))
    referenced_works_count = ma_fields.Int()
    referenced_works = ma_fields.List(ma_fields.Str())
    related_works = ma_fields.List(ma_fields.Str())
    ngrams_url = ma_fields.Method("get_ngrams_url")
    abstract_inverted_index = ma_fields.Function(
        lambda obj: json.loads(obj.abstract_inverted_index).get("InvertedIndex")
        if "abstract_inverted_index" in obj and obj.abstract_inverted_index
        else None
    )
    cited_by_api_url = ma_fields.Str()
    counts_by_year = ma_fields.List(ma_fields.Nested(CountsByYearSchema))
    updated_date = ma_fields.Str()
    created_date = ma_fields.Str(dump_default=None)

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
    meta = ma_fields.Nested(MetaSchema)
    results = ma_fields.Nested(WorksSchema, many=True)
    group_by = ma_fields.Nested(GroupBySchema, many=True)
    group_bys = ma_fields.Nested(GroupBysSchema, many=True)

    class Meta:
        ordered = True
