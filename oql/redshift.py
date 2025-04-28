import re
from copy import deepcopy

import requests
from sqlalchemy import and_, or_, case, cast, desc, func, distinct, Float
from sqlalchemy.orm import aliased, load_only
from sqlalchemy.dialects import postgresql

from settings import OPEN_ALEX_API_KEY
from combined_config import all_entities_config
from extensions import db
from . import models

auth_headers = {"Authorization": f"Bearer {OPEN_ALEX_API_KEY}"}


class RedshiftQueryHandler:
    def __init__(
        self,
        entity,
        filter_works,
        filter_aggs,
        show_columns,
        sort_by_column,
        sort_by_order,
        valid_columns,
        show_underlying_works,
    ):
        self.entity = entity
        self.filter_works = filter_works
        self.filter_aggs = filter_aggs
        self.show_columns = show_columns
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.valid_columns = valid_columns
        self.model_return_columns = []
        self.show_underlying_works = show_underlying_works
        self.entity_config = self.get_entity_config()
        self.works_config = all_entities_config.get("works").get("columns")
        self.filter_joins = []

    def execute(self):
        # Build the base query with all necessary joins
        query = self.build_query()

        # Use the final grouped query for the aggregated results.
        grouped_cte = query.cte()
        total_count = db.session.query(func.count()).select_from(grouped_cte).scalar() or 0
        results = db.session.query(grouped_cte).limit(100).all()

        # Compute works_count as the number of rows returned by the ungrouped query.
        if self.entity == "works" or self.show_underlying_works:
            works_count = total_count
        else:
            self.ungrouped_query = self.ungrouped_query.add_columns(models.Work.paper_id.label("paper_id"))
            subq = self.ungrouped_query.subquery()
            works_count = db.session.query(func.count(distinct(subq.c.paper_id))).scalar()

        return total_count, works_count, results

    def execute_summary(self):
        summary_query = self.build_query()
        
        count, citation_count, open_access_count, mean_fwci, mean_citation_count = db.session.execute(
            summary_query).fetchone()

        return {
            "id": "summary",
            "count": count,
            "sum(cited_by_count)": citation_count,
            "sum(is_oa)": open_access_count,
            "mean(fwci)": mean_fwci,
            "mean(cited_by_count)": mean_citation_count,
            "percent(is_oa)": open_access_count / count if count > 0 else 0
        }

        return summary

    def build_query(self):
        entity_class = models.get_entity_class(self.entity)
        columns_entity_class = entity_class if not self.show_underlying_works else models.Work

        query = self.build_joins(entity_class)
        query = self.set_columns(query, columns_entity_class)
        query = self.apply_work_filters(query)
        query = self.apply_entity_filters(query)  

        if self.entity == "summary":
            query = self.apply_summary(query)
        if self.show_underlying_works:
            query = self.apply_sort(query, entity_class)
            query = self.apply_underlying_works_distinct(query)
        else:
            query = self.apply_sort(query, entity_class)
            query = self.apply_stats(query, entity_class)

        return query

    def build_joins(self, entity_class):
        query = db.session.query(entity_class)

        if self.entity == "works":
            # Special case: If querying works and abstract is in show_columns or filter, add join to Abstract model
            if (
                "abstract" in self.show_columns 
                or "abstract" in self.filter_keys("works")
                or "title_and_abstract" in self.filter_keys("works")
                ):
                query = query.outerjoin(models.Abstract, models.Work.paper_id == models.Abstract.paper_id)

        elif self.entity == "institutions":
            query = (
                query
                .join(
                    models.Affiliation,
                    models.Affiliation.affiliation_id
                    == models.Institution.affiliation_id,
                )
                .join(models.Work, models.Work.paper_id == models.Affiliation.paper_id)
            )

        elif self.entity == "countries":
            query = (
                query
                .join(
                    models.Institution,
                    models.Institution.country_code == models.Country.country_id
                )
                .join(
                    models.Affiliation,
                    models.Affiliation.affiliation_id == models.Institution.affiliation_id
                )
                .join(
                    models.Work,
                    models.Work.paper_id == models.Affiliation.paper_id
                )
            )

        elif self.entity == "continents":
            query = (
                query
                .join(
                    models.Affiliation,
                    models.Affiliation.continent_id == entity_class.continent_id,
                )
                .join(
                    models.Work,
                    models.Work.paper_id == models.Affiliation.paper_id
                )
            )

        elif self.entity == "authors":
            query = (
                query
                .join(
                    models.Affiliation,
                    models.Affiliation.author_id == models.Author.author_id,
                )
                .join(models.Work, models.Work.paper_id == models.Affiliation.paper_id)
            )

        elif self.entity == "funders":
            query = (
                query
                .join(models.WorkFunder, models.WorkFunder.funder_id == entity_class.funder_id)
                .join(models.Work, models.Work.paper_id == models.WorkFunder.paper_id)
            )

        elif self.entity == "sources":
            query = (
                query
                .join(
                    models.Work,
                    models.Work.journal_id == models.Source.source_id,
                )
            )

        elif self.entity == "sdgs":
            query = (
                query
                .join(models.WorkSdg, models.WorkSdg.sdg_id == entity_class.sdg_id)
                .join(models.Work, models.Work.paper_id == models.WorkSdg.paper_id)
            )

        elif self.entity == "topics":
            query = (
                query
                .join(models.WorkTopic, models.WorkTopic.topic_id == entity_class.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
                .join(models.Affiliation, models.Affiliation.paper_id == models.Work.paper_id)
                .join(models.Institution, models.Institution.affiliation_id == models.Affiliation.affiliation_id)
            )

        elif self.entity == "work-types":
            query = (
                query
                .join(models.Work, models.Work.type == entity_class.work_type_id)
            )

        elif self.entity == "languages":
            query = (
                query
                .join(models.Work, models.Work.language == entity_class.language_id)
            )

        elif self.entity == "keywords":
            query = (
                query
                .join(models.WorkKeyword, models.WorkKeyword.keyword_id == entity_class.keyword_id)
                .join(models.Work, models.Work.paper_id == models.WorkKeyword.paper_id)
            )

        elif self.entity == "domains":
            query = (
                query
                .join(models.Topic, models.Topic.domain_id == models.Domain.domain_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )

        elif self.entity == "fields":
            query = (
                query
                .join(models.Topic, models.Topic.field_id == models.Field.field_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )

        elif self.entity == "subfields":
            query = (
                query
                .join(models.Topic, models.Topic.subfield_id == models.Subfield.subfield_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )

        elif self.entity == "publishers":
            query = (
                query
                .join(
                    models.Source,
                    models.Source.publisher_id == models.Publisher.publisher_id
                )
                .join(
                    models.Work,
                    models.Work.journal_id == models.Source.source_id
                )
            )

        elif self.entity == "licenses":
            query = (
                query
                .outerjoin(
                    models.Work,
                    models.Work.license == models.License.license_id
                )
            )

        elif self.entity == "institution-types":
            query = (
                query
                .join(
                    models.Institution,
                    models.Institution.type == models.InstitutionType.institution_type_id
                )
                .join(
                    models.Affiliation,
                    models.Affiliation.affiliation_id == models.Institution.affiliation_id
                )
                .join(
                    models.Work,
                    models.Work.paper_id == models.Affiliation.paper_id
                )
            )

        elif self.entity == "source-types":
            query = (
                query
                .join(
                    models.Source,
                    models.SourceType.source_type_id == models.Source.type  
                )
                .join(
                    models.Work,
                    models.Work.journal_id == models.Source.source_id
                )
            )
        
        # Add addtional join if this is "coauthorship" type filter (see below)
        for filter_obj in self.filter_works:
            key = filter_obj.get("column_id")
            if key and self.is_co_relationship_filter(key):
                query = self.apply_co_relationship_joins(query, filter_obj)

        return query

    def apply_co_relationship_joins(self, query, filter_obj):
        """    
        For authors, we join the Affiliation table (which has paper_id).
        For institutions, we need to join first Affiliation then Institution,
        so that we can filter using Institution attributes.
        """
        if self.entity == "authors":
            # For a co‐relationship query like "get authors who have co‐authored a paper with X",
            # we need to join not only on paper_id but also restrict to the target author X.
            alias_model = models.Affiliation
            target = get_short_id_integer(filter_obj["value"])
            alias = aliased(alias_model)
            query = query.join(
                alias,
                and_(
                    models.Work.paper_id == alias.paper_id,
                    alias.author_id == target
                )
            )
        
        elif self.entity == "funders":
            alias_model = models.WorkFunder
            target = get_short_id_integer(filter_obj["value"])
            alias = aliased(alias_model)
            query = query.join(
                alias,
                and_(
                    models.Work.paper_id == alias.paper_id,
                    alias.funder_id == target
                )
            )

        elif self.entity == "institutions":
            aff_alias = aliased(models.Affiliation)
            inst_alias = aliased(models.Institution)           
            query = query.join((aff_alias, models.Work.paper_id == aff_alias.paper_id))            
            query = query.join(inst_alias, aff_alias.affiliation_id == inst_alias.affiliation_id)

        else:
            raise ValueError(f"Unsupported co-relationship filter for entity {self.entity}: {filter_obj['column_id']}")

        return query

    def is_co_relationship_filter(self, column_id):
        """
        Determines if the given filter column represents a co-relationship filter.
        
        A co-relationship filter is one where the filter's configuration specifies an 
        "objectEntity" that matches the current query's entity type. In such cases,
        the filter is intended to restrict the works (or subject) to those that include at least
        one related record matching the condition, rather than filtering the main join itself.
        
        For example, when filtering on 'authorships.author.id' in an authors query, the configuration
        indicates objectEntity 'authors'. This means we want to restrict works to those having a 
        record for that author, but then still return all authors on those works.
        
        Returns:
            True if the filter should be applied as a co-relationship filter; False otherwise.
        """
        if self.entity in ["countries", "institutions", "keywords"]:
            return False # Works without special casing
        config = self.works_config.get(column_id)
        return bool(config.get("objectEntity") and config.get("objectEntity") == self.entity)
    
    def get_co_relationship_filter_column(self):
        """
        Returns the appropriate filter column on the appropriate model for co-relationship filters based on the current entity.
        This is used in conjunction with apply_co_relationship_joins which sets up the necessary joins.
        """
        if self.entity == "authors":
            return aliased(models.Affiliation).author_id
        elif self.entity == "funders":
            return aliased(models.WorkFunder).funder_id
        
        raise ValueError(f"Unsupported co-relationship filter for entity {self.entity}")

    def set_columns(self, query, entity_class):
        columns_to_select = []
        # print("set_columns")
        show_columns = list(set(self.show_columns + ["id"]))
        show_columns = sorted(show_columns, key=lambda x: not "(" in x) 
        config = self.entity_config if not self.show_underlying_works else self.works_config

        for column in show_columns:
            column_info = config.get(column)
            if not column_info:
                print(f"Skipping {column} - no column config")
                continue

            redshift_column = column_info.get("redshiftDisplayColumn", "")
            if not redshift_column:
                print(f"Skipping {column} - no redshiftDisplayColumn")
                continue
                
            if redshift_column.startswith(("count(", "sum(", "mean(", "percent(")):
                # print(f"Skipping {column} - agg")
                continue # Skip aggregators, these are handled in apply_stats()

            if column == "abstract":
                columns_to_select.append(models.Abstract.abstract.label("abstract"))
                continue
            
            if hasattr(entity_class, redshift_column):
                attr = getattr(entity_class, redshift_column)
                if isinstance(attr, property):
                    # print(f"Skipping {column} - {redshift_column} is property")
                    continue
                col_ = getattr(entity_class, redshift_column).label(column)
                columns_to_select.append(col_)


        if self.show_underlying_works:
            # Fix to prevent SQLAlchemy from dropping joined tables because we're only looking at Work columns
            # for a query whose base is with another entity.
            entity_class = models.get_entity_class(self.entity)
            columns_to_select.append(entity_class.id.label("entity_id"))

        self.model_return_columns = columns_to_select
        return query.with_entities(*columns_to_select)

    def filter_keys(self, entity):
        """Recursively walks all filters for either "works" or "entity" and returns a list of all filter column ids found."""
        keys = []
        filters = self.filter_works if entity == "works" else self.filter_aggs
        
        def walk_filters(filters):
            for _filter in filters:
                if "join" in _filter and "filters" in _filter:
                    walk_filters(_filter["filters"])
                else:
                    column_id = _filter.get("column_id")
                    if column_id:
                        keys.append(column_id)
        
        walk_filters(filters)
        return list(set(keys))

    def apply_work_filters(self, query):
        return self.apply_filters(query, "work")

    def apply_entity_filters(self, query):
        return self.apply_filters(query, "entity")

    def apply_filters(self, query, type):
        condition = None
        if type == "work":
            condition = self.build_filters_condition(self.filter_works, "and", "work")
        elif type == "entity":    
            condition = self.build_filters_condition(self.filter_aggs, "and", "entity")

        #print(f"Applying condition for {type}")
        #print(condition, flush=True)

        if condition is not None:
            query = query.filter(condition)
        
        return query       

    def build_filters_condition(self, filters, join, type):
        """
        Recursive function to build nested dis/conjunctions of filter objects.
        :filters - List of filter objects
        :join - String in ["and", "or"] -- how to join each filter condition
        :type - String in ["works", "entity"] - chooses which base function to build conditions
        Returns a single condition joining all condition parts with either "and"/"or"
        """
        conditions = []
        #print("build_filters_condition: filters:")
        #print(filters)
        #print(f"build_filters_condition: type: {type}")

        for _filter in filters:
            new_condition = None
            if "join" in _filter and "filters" in _filter:  # Compound filter
                # Recurse for nested filters
                new_condition = self.build_filters_condition(_filter["filters"], _filter["join"], type)
            else:
                if type == "work":
                    new_condition = self.build_work_filter_condition(_filter)
                elif type == "entity":
                    new_condition = self.build_entity_filter_condition(_filter)

            if new_condition is not None:
                conditions.append(new_condition)

        #print("build_filters_condition: conditions:")
        #print(conditions)

        # Combine all conditions using and_/or_
        # defaults to "and" if bad join value is passed
        return or_(*conditions) if join == "or" else and_(*conditions)
            
    def build_work_filter_condition(self, filter):
        """ Returns a `condition` which represents `filter` for works."""
        work_class = getattr(models, "Work")

        key = filter.get("column_id")
        config = self.works_config.get(key)

        value = filter.get("value")
        operator = filter.get("operator") or config.get("defaultOperator")

        #print("Building work filter: ")
        #print(filter, flush=True)

        # ensure is valid filter
        if key is None:
            raise(ValueError("Invalid work filter: missing key"))
        if value is None:
            raise(ValueError("Invalid work filter: missing value"))

        # setup
        redshift_column = config.get("redshiftFilterColumn")
        column_type = config.get("type")
        is_object_entity = config.get("objectEntity")
        model_column = getattr(
            work_class, redshift_column, None
        )  if redshift_column else None # primary column to filter against

        #print(config, flush=True)

        if self.is_co_relationship_filter(key):
            # "Co-relationship" filters use additional join (see below)
            value = get_short_id_integer(value)
            column = self.get_co_relationship_filter_column()
            operator = {"includes": "is", "does not include": "is not"}.get(operator, operator)
            return build_operator_condition(column, operator, value)

        elif column_type == "number":
            return build_number_condition(model_column, operator, value)

        elif key in ["type", "language", "license", "keywords.id", "primary_location.source.type"]:
            value = get_short_id_text(value).lower()

        elif key == "authorships.countries":
            value = get_short_id_text(value).upper()  # Country codes must be uppercase

        elif key in ["id","authorships.institutions.id"]:
            value = get_short_id_integer(value)
        
        elif key == "abstract":
            model_column = models.Abstract.abstract

        elif key == "title_and_abstract":
            model_column = models.Work.original_title
            return or_(
                build_operator_condition(models.Work.original_title, operator, value),
                build_operator_condition(models.Abstract.abstract, operator, value)
            )
        
        elif key == "authorships.institutions.lineage":
            value = get_short_id_integer(value)
            join_condition = models.PaperInstitutionLineage.paper_id == work_class.paper_id
            filter_column = models.PaperInstitutionLineage.ancestor_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.type":
            value = get_short_id_text(value)
            join_condition = models.AffiliationTypeDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationTypeDistinct.type
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)
        
        elif key == "authorships.author.id":
            value = get_short_id_integer(value)
            join_condition = models.AffiliationAuthorDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationAuthorDistinct.author_ids
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.ror":
            join_condition = and_(
                models.Work.paper_id == models.Affiliation.paper_id,
                models.Affiliation.affiliation_id == models.Institution.affiliation_id,
            )
            filter_condition = models.Institution.ror == value
            return and_(join_condition, filter_condition)

        elif key == "authorships.author.orcid":
            join_condition = and_(
                models.Work.paper_id == models.Affiliation.paper_id,
                models.Affiliation.author_id == models.Author.author_id,
            )
            filter_condition = models.Author.orcid == value
            return and_(join_condition, filter_condition)

        elif key == "grants.funder" and self.entity == "funders":
            # TODO check this is still needed / working
            # co-relationship: The extra join (added in build_joins) has restricted works to those funded by X.
            # Now, filter out X from the final results.
            value = get_short_id_integer(value)
            return build_operator_condition(models.Funder.funder_id, "is not", value)

        elif key == "sustainable_development_goals.id":
            value = get_short_id_integer(value)
            join_condition = models.WorkSdg.paper_id == work_class.paper_id
            filter_column = models.WorkSdg.sdg_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.continent":
            wiki_code = get_short_id_text(value)
            value = convert_wiki_to_continent_id(wiki_code)
            join_condition = models.AffiliationContinentDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationContinentDistinct.continent_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "related_to_text":
            print(f"related_to_text GET: https://api.openalex.org/text/related-authors?text={value}")
            print("Headers: ", auth_headers)
            r = requests.get(f"https://api.openalex.org/text/related-works?text={value}", headers=auth_headers)
            if r.status_code == 200:
                results = r.json()
                related_paper_ids = [result["work_id"] for result in results]
                return work_class.paper_id.in_(related_paper_ids)
            else:
                print(f"Response code: {r.status_code}")
                raise ValueError(f"Failed to get related works for text: {value}")
       
        elif column_type in ["object", "array"] or is_object_entity:
            # TODO check that this case is still relevant
            value = get_short_id_integer(value)

        # Return value for all cases that just set these three values, or default case 
        return build_operator_condition(model_column, operator, value)

    def build_entity_filter_condition(self, filter):
        """ Returns a `condition` which represents `filter` for entities."""

        entity_class = models.get_entity_class(self.entity)

        key = filter.get("column_id")
        value = filter.get("value")
        operator = filter.get("operator") or "is"

        # ensure is valid filter
        if key is None:
            raise(ValueError("Invalid entity filter: missing key"))
        if value is None:
            raise(ValueError("Invalid entity filter: missing value"))

        # do not filter stats
        if key.startswith(("count(", "sum(", "mean(", "percent(")):
            return None

        # setup
        redshift_column = self.entity_config.get(key).get("redshiftFilterColumn")
        column_type = self.entity_config.get(key).get("type")
        is_object_entity = self.entity_config.get(key).get("objectEntity")
        is_search_column = self.entity_config.get(key).get("isSearchColumn")

        if redshift_column:
            model_column = getattr(entity_class, redshift_column, None)

        #print(f"Building entity filter: redshift_column: {redshift_column}, column_type: {column_type}, is_object_entity: {is_object_entity}, is_search_column: {is_search_column}, model_column: {model_column}")

        if column_type == "number":
            return build_number_condition(model_column, operator, value)

        elif column_type == "boolean":
            value = get_boolean_value(value)
            return build_operator_condition(model_column, operator, value)

        elif is_search_column:
            return model_column.ilike(f"%{value}%")

        elif key == "affiliations.institution.type":
            value = get_short_id_text(value)
            return build_operator_condition(model_column, operator, value)
        
        elif key == "id" and self.entity in ["continents", "countries", "institution-types", "languages", "licenses", "source-types", "work-types"]:
            value = get_short_id_text(value)
            if self.entity in ["countries", "continents"]:
                value = value.upper()
            else:
                value = value.lower()
            return build_operator_condition(model_column, operator, value)

        elif key == "id":
            value = get_short_id_integer(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "continent":
            value = convert_wiki_to_continent_id(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "host_organization" and self.entity == "sources":
            value = get_short_id_integer(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "country_code" or key == "last_known_institutions.country_code":
            value = get_short_id_text(value).upper()
            return build_operator_condition(model_column, operator, value)

        elif key in ["type", "last_known_institutions.type"]:
            value = get_short_id_text(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "related_to_text" and self.entity == "authors":
            print(f"related_to_text GET: https://api.openalex.org/text/related-authors?text={value}")
            print("Headers: ", auth_headers)
            r = requests.get(f"https://api.openalex.org/text/related-authors?text={value}", headers=auth_headers)
            if r.status_code == 200:
                results = r.json()
                related_author_ids = [result["author_id"] for result in results]
                return entity_class.author_id.in_(related_author_ids)
            else:
                print(f"Response code: {r.status_code}")
                raise ValueError(f"Failed to get related authors for text: {value}")
        
        # specialized filters
        elif key == "last_known_institutions.id" and self.entity == "authors":
            value = get_short_id_integer(value)
            join_condition = and_(
                models.AuthorLastKnownInstitutions.author_id == entity_class.author_id,
                models.AuthorLastKnownInstitutions.rank == 1  # Most recent affiliation
            )
            filter_condition = build_operator_condition(models.AuthorLastKnownInstitutions.affiliation_id, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "affiliations.institution.id" and self.entity == "authors":
            value = get_short_id_integer(value)
            join_condition = models.Affiliation.author_id == entity_class.author_id
            filter_condition = build_operator_condition(models.Affiliation.affiliation_id, operator, value)
            return and_(join_condition, filter_condition)

        elif column_type in ["object", "array"] and is_object_entity:
            value = get_short_id_text(value) if column_type == "object" else value
            value = value.upper() if "country_code" in key else value
            return build_operator_condition(model_column, operator, value)

        else:
            return build_operator_condition(model_column, operator, value)

    def apply_summary(self, query):

        summary_query = query.with_entities(
            func.count().label("count"),
            func.sum(models.Work.cited_by_count).label("sum(cited_by_count)"),
            func.sum(case([(models.Work.oa_status.in_(["gold", "hybrid", "green"]), 1)], else_=0)).label("sum(is_oa)"),
            func.avg(models.Work.fwci).label("mean(fwci)"),
            func.avg(models.Work.cited_by_count).label("mean(cited_by_count)")
        )      
        return summary_query

    def apply_sort(self, query, entity_class):
        if self.sort_by_column:
            config  = self.entity_config if not self.show_underlying_works else self.works_config
            
            sort_column = config.get(self.sort_by_column).get(
                "redshiftDisplayColumn"
            )
            if (
                self.sort_by_column == "count(works)"
                or self.sort_by_column == "mean(fwci)"
                or self.sort_by_column == "percent(is_open_access)"
            ):
                return query
            else:
                model_column = getattr(entity_class, sort_column, None)

            if model_column:
                query = (
                    query.order_by(model_column)
                    if self.sort_by_order == "asc"
                    else query.order_by(desc(model_column))
                )
        return query

    def apply_stats(self, query, entity_class):
        aggregator_columns = ["count(works)", "sum(citations)", "mean(fwci)", "percent(is_open_access)"]
        
        grouping_applied = False

        # Save a copy of the ungrouped query before any grouping/aggregations for underlying works query/count
        self.ungrouped_query = query._clone()
        
        for column in self.show_columns:
            if column not in aggregator_columns:
                continue

            work_class = getattr(models, "Work")  
            stat, related_entity = parse_stats_column(column)
            # e.g. "count(works)" -> stat="count", related_entity="works"

            # We'll build 'stat_function' differently per aggregator.
            # We'll also track extra group-by columns if needed.
            stat_function = None
            extra_groupbys = []

            if column == "count(works)":            
                if self.entity in ["authors", "countries", "institutions"]:
                    affiliation_class = getattr(models, "Affiliation")
                    stat_function = func.count(func.distinct(affiliation_class.paper_id))
                
                elif self.entity == "keywords":
                    stat_function = func.count(work_class.paper_id)
                    extra_groupbys.append(entity_class.keyword_id)
                
                elif self.entity == "languages":
                    stat_function = func.count(work_class.paper_id)
                    extra_groupbys.append(work_class.language)
                
                elif self.entity == "sources":
                    stat_function = func.count(work_class.paper_id)
                    extra_groupbys.append(entity_class.source_id)
                
                elif self.entity == "topics":
                    work_topic_class = getattr(models, "WorkTopic")
                    query = query.filter(work_topic_class.topic_rank == 1)
                    stat_function = func.count(func.distinct(work_topic_class.paper_id))
                    extra_groupbys.append(entity_class.topic_id)
                
                else:
                    # Default applies to ["continents", "domains", "fields", "funders", "institution-types", "licenses", "publishers", "sdgs", "source-types", "subfields", "work-types"]:
                    stat_function = func.count(work_class.paper_id)

            elif column == "sum(citations)":
                stat_function = func.sum(work_class.cited_by_count)

            elif column == "mean(fwci)":
                stat_function = func.avg(work_class.fwci)

            elif column == "percent(is_open_access)":
                open_access_case = case(
                    [(work_class.oa_status.in_(["gold", "hybrid", "green"]), 1)],
                    else_=0
                )
                stat_function = (
                    func.sum(cast(open_access_case, Float)) /
                    func.count(work_class.paper_id).cast(Float)
                )

            # Apply "group_by + add_columns + filter_stats + sort" determined above:
            # Combine existing group-by columns (from set_columns) with any extra
            all_groupbys = self.model_return_columns + extra_groupbys
            if all_groupbys:
                query = query.group_by(*all_groupbys)
                grouping_applied = True

            # label -> e.g. "count(works)" or "sum(citations)"
            query = query.add_columns(stat_function.label(column))

            # apply aggregator filter (HAVING) if it exists
            agg_condition = self.build_aggregator_condition(self.filter_aggs, column, stat_function)
            if agg_condition is not None:
                query = query.having(agg_condition)

            # apply aggregator sorting if needed
            if self.sort_by_column == column:
                query = self.sort_from_stat(query, self.sort_by_order, stat_function)

        # If no aggregator columns were applied but we're querying entities other than summary,
        # we need to ensure distinct rows for the entity
        if not grouping_applied and self.entity != "summary":
            query = query.distinct()

        return query

    def apply_underlying_works_distinct(self, query):
        # Underlying Works include a column for entity_id, aggregate on that column
        # so that we can return distinct works rows.
        new_columns = []
        for col in self.model_return_columns:
            if hasattr(col, 'name') and col.name == 'entity_id':
                # Instead of just displaying one entity_id, count how many entities are associated with each work
                new_columns.append(func.count(col).label('entity_count'))
            else:
                new_columns.append(col)
        
        # Group by all columns except entity_id
        group_by_columns = [col for col in self.model_return_columns 
                            if not (hasattr(col, 'name') and col.name == 'entity_id')]
        
        # Update the query to use these new columns and proper grouping
        query = query.with_entities(*new_columns).group_by(*group_by_columns)
        return query

    def build_aggregator_condition(self, filter_list, agg_col, stat_function, join_type="and"):
        """
        Recursively build a single SQLAlchemy condition for aggregator filters
        referencing `agg_col` (like "count(works)").
        :param filter_list: A list of filter dicts (or nested filter blocks).
        :param agg_col: The aggregator column ID (e.g. "count(works)") we are applying.
        :param stat_function: The SQLAlchemy function for that aggregator (e.g. func.count(...)).
        :param join_type: "and" or "or" indicates how we combine subconditions.
        :return: A single SQLAlchemy condition or None if no relevant aggregator filters.
        """
        if not filter_list:
            return None

        conditions = []
        for node in filter_list:
            # If it's a nested block: { "join": "...", "filters": [...] }
            if "join" in node and "filters" in node:
                sub_cond = self.build_aggregator_condition(
                    node["filters"], agg_col, stat_function, node["join"]
                )
                if sub_cond is not None:
                    conditions.append(sub_cond)
            else:
                # It's a leaf node
                col_id = node.get("column_id")
                operator = node.get("operator", "is")
                value = node.get("value")

                # Only build a condition if col_id matches the aggregator we're processing
                if col_id == agg_col:
                    cond = self.build_simple_aggregator_condition(stat_function, operator, value)
                    if cond is not None:
                        conditions.append(cond)

        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        # Combine them with AND or OR
        if join_type == "or":
            return or_(*conditions)
        else:
            return and_(*conditions)

    def build_simple_aggregator_condition(self, stat_function, operator, value):
        """
        Build a single leaf aggregator condition, e.g. stat_function > value.
        Equivalent to your filter_stats logic, but returns a condition instead
        of modifying the query directly.
        """
        # Convert value to int if needed, or handle numeric vs. string
        value = int(value)  # adjust if operator can be string-based
        if operator in ["is greater than", ">"]:
            return stat_function > value
        elif operator in ["is greater than or equal to", ">="]:
            return stat_function >= value
        elif operator in ["is less than", "<"]:
            return stat_function < value
        elif operator in ["is less than or equal to", "<="]:
            return stat_function <= value
        elif operator in ["is"]:
            return stat_function == value
        elif operator in ["is not", "!="]:
            return stat_function != value
        else:
            return None

    @staticmethod
    def sort_from_stat(query, sort_by_order, sort_func):
        if sort_by_order:
            if sort_by_order == "desc":
                query = query.order_by(sort_func.desc().nulls_last())
            else:
                query = query.order_by(sort_func.asc().nulls_last())
        return query

    def get_entity_config(self):
        entity_for_config = "works" if self.entity == "summary" else self.entity
        return all_entities_config.get(entity_for_config).get("columns")

    def get_sql(self):
        query = self.build_query()
        return str(query.statement.compile(
                    dialect=postgresql.dialect(), 
                    compile_kwargs={"literal_binds": True}))


def build_operator_condition(column, operator, value):
    #print("model_column / operator / value ")
    #print(f"{column} / {operator} / {value}", flush=True)
    if operator == "is":
        return column == value
    elif operator == "is not":
        return column != value

    elif operator == "includes":
        return column.like(f"%|{value}|%")
    elif operator == "does not include":
        return column.notlike(f"%|{value}|%")

    elif operator == "contains":
        return column.ilike(f"%{value}%")
    elif operator == "does not contain":
        return column.notilike(f"%{value}%")

    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_number_condition(column, operator, value):
    if type(value) == str:
        try:
            value = int(value)
        except:
            return build_number_condition_from_string(column, operator, value)

    if operator in ["is greater than", ">"]:
        return column > value
    elif operator in ["is less than", "<"]:
        return column < value
    elif operator in ["is greater than or equal to", ">="]:
        return column >= value
    elif operator in ["is less than or equal to", "<="]:
        return column <= value
    elif operator == "is not":
        return column != value
    elif operator == "is":
        return column == value
    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_number_condition_from_string(column, operator, value):
    if operator not in ["is", "is not"]:
        raise ValueError(f"Unsupported operator for number ranges: {operator}")

    if "-" in value:
        value = value.split("-")
        if len(value) != 2:
            raise ValueError(f"Invalid range: {value} (only one '-' allowed per range)")
        
        # Handle open-ended ranges like "2018-" or "-2018"
        if value[0] == "":  # Format: "-2018"
            try:
                end = int(value[1])
                return column <= end if operator == "is" else column > end
            except ValueError:
                raise ValueError(f"Invalid range: {value} (End of range must be an integer)")
        elif value[1] == "":  # Format: "2018-"
            try:
                start = int(value[0])
                return column >= start if operator == "is" else column < start
            except ValueError:
                raise ValueError(f"Invalid range: {value} (Start of range must be an integer)")
        
        # Handle regular ranges like "2018-2020"
        try:
            start, end = int(value[0]), int(value[1])
        except ValueError:
            raise ValueError(f"Invalid range: {value} (Start and end of ranges must be integers)")

        return and_(column >= start, column <= end) if operator == "is" else or_(column < start, column > end)
    
    # parse values like ">2000". value can start with ">", "<", ">=", or "<=" and the rest must be a number
    operators = [">=", "<=", ">", "<"]  # check longer operators first
    found_op = None
    for op in operators:
        if value.startswith(op):
            found_op = op
            try:
                num_value = int(value[len(op):])
            except ValueError:
                raise ValueError(f"Invalid number after {op}: {value}")
            break

    if found_op is None:
        raise ValueError(f"Invalid number condition: {value}")
    
    if found_op == ">":
        return column > num_value if operator == "is" else column <= num_value
    if found_op == "<":
        return column < num_value if operator == "is" else column >= num_value
    if found_op == ">=":
        return column >= num_value if operator == "is" else column < num_value
    if found_op == "<=":
        return column <= num_value if operator == "is" else column > num_value


def get_boolean_value(value):
    if isinstance(value, bool):
        return value
    elif value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False


def get_short_id_text(value):
    value = value.split("/")[-1].lower()
    return value


def get_short_id_integer(value):
    if isinstance(value, int):
        return value
    value = get_short_id_text(value)
    value = re.sub(r"[a-zA-Z]", "", value)
    value = int(value)
    return value


def parse_stats_column(column):
    # use format like count(works) to get stat and entity
    #print(column)
    stat = column.split("(")[0]
    entity = column.split("(")[1].split(")")[0]
    return stat, entity


def convert_wiki_to_continent_id(value):
    value = get_short_id_text(value)
    value = value.upper()
    mapping = {
        "Q15": 1,
        "Q51": 2,
        "Q48": 3,
        "Q46": 4,
        "Q49": 5,
        "Q55643": 6,
        "Q18": 7,
    }
    return mapping.get(value)
