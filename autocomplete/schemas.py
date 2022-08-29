from elasticsearch_dsl import MultiSearch, Search
from iso3166 import countries
from marshmallow import Schema, fields, pre_dump

from core.schemas import GroupBySchema, MetaSchema
from settings import WORKS_INDEX


class AutoCompleteSchema(Schema):
    id = fields.Str()
    display_name = fields.Str()
    hint = fields.Method("get_hint", dump_default=None)
    cited_by_count = fields.Int()
    entity_type = fields.Method("get_entity_type", dump_default=None)
    external_id = fields.Method("get_external_id", dump_default=None)

    def get_hint(self, obj):
        if "authors" in obj.meta.index:
            return obj.hint if "hint" in obj else None
        elif "concepts" in obj.meta.index:
            return obj.description if "description" in obj else None
        elif "institutions" in obj.meta.index:
            return self.get_location(obj)
        elif "venues" in obj.meta.index:
            if "publisher" in obj and obj.publisher is not None:
                return obj.publisher
            else:
                return "publisher unknown"
        elif "works" in obj.meta.index:
            return self.build_author_string(obj)

    @pre_dump(pass_many=True)
    def author_hint_prep(self, data, many, **kwargs):
        """This function maps a work title and publication year to an author result as a hint."""
        ms = MultiSearch(index=WORKS_INDEX)
        has_hints = False
        # first pass, build search hints with multisearch
        for d in data:
            if "authors" in d.meta.index:
                has_hints = True
                s = Search()
                s = s.filter("term", authorships__author__id=d.id)
                s = s.sort("-cited_by_count")
                s = s.extra(size=1)
                s = s.source(["title", "publication_year"])
                ms = ms.add(s)

        # second pass, map hints to objects
        if has_hints:
            responses = ms.execute()
            for d, response in zip(data, responses):
                for h in response:
                    d.hint = f"{h.title} ({h.publication_year})"
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
                elif author and author.author.display_name:
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
            "institutions": "institution",
            "venues": "venue",
            "works": "work",
        }
        for key, value in entities.items():
            if key in obj.meta.index:
                return value

    def get_external_id(self, obj):
        entities = {
            "authors": "orcid",
            "concepts": "wikidata",
            "institutions": "ror",
            "venues": "issn_l",
            "works": "doi",
        }
        for key, value in entities.items():
            if key in obj.meta.index:
                return getattr(obj, value, None)

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
