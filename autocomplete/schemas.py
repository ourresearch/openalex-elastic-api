from elasticsearch_dsl import MultiSearch, Search
from iso3166 import countries
from marshmallow import Schema, fields, pre_dump

from core.schemas import GroupBySchema, MetaSchema
from settings import WORKS_INDEX


class AutoCompleteSchema(Schema):
    id = fields.Method("get_id")
    display_name = fields.Str()
    hint = fields.Method("get_hint", dump_default=None)
    cited_by_count = fields.Int()
    works_count = fields.Int(default=None)
    entity_type = fields.Method("get_entity_type", dump_default=None)
    external_id = fields.Method("get_external_id", dump_default=None)
    filter_key = fields.Method("get_filter_key", dump_default=None)

    def get_hint(self, obj):
        if "authors" in obj.meta.index:
            return obj.hint if "hint" in obj else None
        elif "institutions" in obj.meta.index:
            return self.get_location(obj)
        elif "sources" in obj.meta.index:
            if (
                "host_organization_name" in obj
                and obj.host_organization_name is not None
            ):
                return obj.host_organization_name
            else:
                return "host organization unknown"
        elif "works" in obj.meta.index:
            return self.build_author_string(obj)
        else:
            return obj.description if "description" in obj else None

    @pre_dump(pass_many=True)
    def author_hint_prep(self, data, many, **kwargs):
        """This function sets the author hint."""
        data = self.set_author_hint_institution(data)
        return data

    def set_author_hint_institution(self, data):
        for obj in data:
            if "authors" in obj.meta.index:
                institution_display_name = (
                    obj.last_known_institution.display_name
                    if obj.last_known_institution
                    else None
                )
                institution_country_code = (
                    obj.last_known_institution.country_code
                    if obj.last_known_institution
                    else None
                )
                if institution_display_name and institution_country_code:
                    obj.hint = f"{institution_display_name}, {self.get_country_name(institution_country_code)}"
                elif institution_display_name:
                    obj.hint = institution_display_name
                else:
                    obj.hint = None
        return data

    def get_location(self, obj):
        if "geo" in obj:
            city = obj.geo.city if "city" in obj.geo else None
            country_code = obj.geo.country_code if "country_code" in obj.geo else None
            country_name = self.get_country_name(country_code) if country_code else None

            if city and country_name:
                location = f"{city}, {country_name}"
            elif not city and country_name:
                location = country_name
            else:
                location = None
        else:
            location = None
        return location

    @staticmethod
    def get_country_name(country_code):
        if country_code.lower() == "us":
            country_name = "USA"
        elif country_code.lower() == "gb":
            country_name = "UK"
        else:
            c = countries.get(country_code.lower())
            country_name = c.name
        return country_name

    @staticmethod
    def build_author_string(obj):
        authors_unknown = "authors unknown"

        if "authorships" in obj:
            i = 0
            author_names = []
            for author in obj.authorships:
                if i > 2:
                    author_names.append("et al.")
                    break
                elif author and author.author and author.author.display_name:
                    author_names.append(author.author.display_name)
                    i = i + 1
            if author_names:
                return ", ".join(author_names)
            else:
                return authors_unknown
        else:
            return authors_unknown

    def get_entity_type(self, obj):
        entities = {
            "authors": "author",
            "concepts": "concept",
            "countries": "country",
            "funders": "funder",
            "institutions": "institution",
            "publishers": "publisher",
            "sources": "source",
            "sdgs": "sdg",
            "topics": "topic",
            "types": "type",
            "works": "work",
        }
        for key, value in entities.items():
            if key in obj.meta.index:
                return value

    def get_external_id(self, obj):
        entities = {
            "authors": "orcid",
            "concepts": "wikidata",
            "countries": "country_code",
            "funders": "ids__ror",
            "institutions": "ror",
            "sources": "issn_l",
            "topics": "wikipedia",
            "works": "doi",
        }
        if "funders" in obj.meta.index:
            return obj.ids.ror if "ror" in obj.ids else None
        elif "publishers" in obj.meta.index:
            return obj.ids.wikidata if "wikidata" in obj.ids else None
        elif "sdgs" in obj.meta.index:
            return obj.ids.un if "un" in obj.ids else None
        elif "topics" in obj.meta.index:
            return obj.ids.wikipedia if "wikipedia" in obj.ids else None
        else:
            for key, value in entities.items():
                if key in obj.meta.index:
                    return getattr(obj, value, None)

    @staticmethod
    def get_filter_key(obj):
        """Filter key you would need to filter in works, based on the index."""
        mapping = {
            "authors": "authorships.author.id",
            "concepts": "concepts.id",
            "countries": "authorships.countries",
            "funders": "grants.funder",
            "institutions": "authorships.institutions.lineage",
            "languages": "language",
            "publishers": "primary_location.source.host_organization_lineage",
            "sources": "primary_location.source.id",
            "topics": "topics.id",
            "types": "type",
            "sdgs": "sustainable_development_goals.id",
            "works": "id",
            "work-type": "type",
        }

        for index, key in mapping.items():
            if index in obj.meta.index:
                return key

    def get_id(self, obj):
        return obj.id

    class Meta:
        ordered = True


class MessageSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(AutoCompleteSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True


class AutoCompleteCustomSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    cited_by_count = fields.Int()
    works_count = fields.Int(default=None)
    entity_type = fields.Str()
    external_id = fields.Str()

    class Meta:
        ordered = True


class MessageAutocompleteCustomSchema(Schema):
    meta = fields.Nested(MetaSchema)
    results = fields.Nested(AutoCompleteCustomSchema, many=True)
    group_by = fields.Nested(GroupBySchema, many=True)

    class Meta:
        ordered = True
