import re

import requests
from sqlalchemy import and_, or_, case, cast, desc, func, Float
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import aliased
from sqlalchemy.dialects import postgresql

from combined_config import all_entities_config
from extensions import db
from oql import models


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
    ):
        self.entity = entity
        self.filter_works = filter_works
        self.filter_aggs = filter_aggs
        self.show_columns = show_columns
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.valid_columns = valid_columns
        self.model_return_columns = []
        self.entity_config = self.get_entity_config()
        self.works_config = all_entities_config.get("works").get("columns")

    def execute(self):
        query = self.build_query()

        count_query = db.session.query(func.count()).select_from(query.subquery())
        total_count = db.session.execute(count_query).scalar()

        results = query.limit(100).all()

        return total_count, results

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
        entity_class = get_entity_class(self.entity)

        query = self.build_joins(entity_class)
        query = self.set_columns(query, entity_class)
        query = self.apply_work_filters(query)
        query = self.apply_entity_filters(query)  

        if self.entity != "summary":
            query = self.apply_sort(query, entity_class)  
            query = self.apply_stats(query, entity_class)

        return query

    def get_sql(self):
        query = self.build_query()
        return str(query.statement.compile(
                    dialect=postgresql.dialect(), 
                    compile_kwargs={"literal_binds": True}))

    def build_joins(self, entity_class):
        columns_to_select = [entity_class]

        if self.entity == "institutions":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(
                    models.Affiliation,
                    models.Affiliation.affiliation_id
                    == models.Institution.affiliation_id,
                )
                .join(models.Work, models.Work.paper_id == models.Affiliation.paper_id)
            )
        elif self.entity == "countries":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
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
                db.session.query(*columns_to_select)
                .distinct()
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
                db.session.query(*columns_to_select)
                .distinct()
                .join(
                    models.Affiliation,
                    models.Affiliation.author_id == models.Author.author_id,
                )
                .join(models.Institution,
                      models.Institution.affiliation_id == models.Affiliation.affiliation_id)
                .join(models.Work, models.Work.paper_id == models.Affiliation.paper_id)
            )
        elif self.entity == "funders":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.WorkFunder, models.WorkFunder.funder_id == entity_class.funder_id)
                .join(models.Work, models.Work.paper_id == models.WorkFunder.paper_id)
            )
        elif self.entity == "sources":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(
                    models.Work,
                    models.Work.journal_id == models.Source.source_id,
                )
            )
        elif self.entity == "sdgs":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.WorkSdg, models.WorkSdg.sdg_id == entity_class.sdg_id)
                .join(models.Work, models.Work.paper_id == models.WorkSdg.paper_id)
            )
        elif self.entity == "topics":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.WorkTopic, models.WorkTopic.topic_id == entity_class.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
                .join(models.Affiliation, models.Affiliation.paper_id == models.Work.paper_id)
                .join(models.Institution, models.Institution.affiliation_id == models.Affiliation.affiliation_id)
            )
        elif self.entity == "work-types":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.Work, models.Work.type == entity_class.work_type_id)
            )
        elif self.entity == "languages":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.Work, models.Work.language == entity_class.language_id)
            )
        elif self.entity == "keywords":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.WorkKeyword, models.WorkKeyword.keyword_id == entity_class.keyword_id)
                .join(models.Work, models.Work.paper_id == models.WorkKeyword.paper_id)
            )
        elif self.entity == "domains":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.Topic, models.Topic.domain_id == models.Domain.domain_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )
        elif self.entity == "fields":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.Topic, models.Topic.field_id == models.Field.field_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )
        elif self.entity == "subfields":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(models.Topic, models.Topic.subfield_id == models.Subfield.subfield_id)
                .join(models.WorkTopic, models.WorkTopic.topic_id == models.Topic.topic_id)
                .join(models.Work, models.Work.paper_id == models.WorkTopic.paper_id)
            )
        elif self.entity == "publishers":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
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
                db.session.query(*columns_to_select)
                .distinct()
                .outerjoin(
                    models.Work,
                    models.Work.license == models.License.license_id
                )
            )
        elif self.entity == "institution-types":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
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
                db.session.query(*columns_to_select)
                .distinct()
                .join(
                    models.Source,
                    models.SourceType.source_type_id == models.Source.type  
                )
                .join(
                    models.Work,
                    models.Work.journal_id == models.Source.source_id
                )
            )  
        else:
            query = db.session.query(*columns_to_select)

        self.model_return_columns = columns_to_select
        return query

    def set_columns(self, query, entity_class):
        columns_to_select = []

        for column in self.show_columns:
            column_info = self.entity_config.get(column)
            if not column_info:
                continue

            redshift_column = column_info.get("redshiftDisplayColumn")
            if redshift_column.startswith("count("):
                continue # Handle aggregate columns elsewhere

            if is_model_property(redshift_column, entity_class):
                continue # Skip model properties

            if hasattr(entity_class, redshift_column):
                columns_to_select.append(getattr(entity_class, redshift_column))

        return query.with_entities(*columns_to_select)

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

        print(f"Applying condition for {type}")
        print(condition, flush=True)

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
        print("build_filters_condition: filters:")
        print(filters)
        print(f"build_filters_condition: type: {type}")

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

        print("build_filters_condition: conditions:")
        print(conditions)

        # Combine all conditions using and_/or_
        # defaults to "and" if bad join value is passed
        return or_(*conditions) if join == "or" else and_(*conditions)
            

    def build_work_filter_condition(self, filter):
        """ Returns a `condition` which represents `filter` for works."""
        work_class = getattr(models, "Work")

        key = filter.get("column_id")
        value = filter.get("value")
        operator = filter.get("operator") or "is"

        print("Building work filter: ")
        print(filter, flush=True)

        # ensure is valid filter
        if key is None:
            raise(ValueError("Invalid work filter: missing key"))
        if value is None:
            raise(ValueError("Invalid work filter: missing value"))

        # setup
        redshift_column = self.works_config.get(key).get("redshiftFilterColumn")
        column_type = self.works_config.get(key).get("type")
        is_object_entity = self.works_config.get(key).get("objectEntity")
        model_column = getattr(
            work_class, redshift_column, None
        )  # primary column to filter against

        if not redshift_column:
            raise(ValueError(f"Column {key} missing 'redshiftFilterColumn' in entity config"))

        if column_type == "number":
            return build_number_condition(model_column, operator, value)

        elif ".search" in key:
            return model_column.ilike(f"%{value}%")

        elif key == "keywords.id":
            value = get_short_id_text(value)
            join_condition = models.WorkKeyword.paper_id == work_class.paper_id
            filter_column = models.WorkKeyword.keyword_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)            

        elif key == "type" or key == "primary_location.source.type":
            value = get_short_id_text(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "authorships.institutions.id":
            value = get_short_id_integer(value)
            join_condition = models.AffiliationDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationDistinct.affiliation_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.type":
            value = get_short_id_text(value).capitalize()
            affiliation_class = aliased(getattr(models, "Affiliation"))
            institution_class = aliased(getattr(models, "Institution"))
            join_condition = and_(
                affiliation_class.paper_id == work_class.paper_id,
                institution_class.affiliation_id == affiliation_class.affiliation_id,
            )
            filter_condition = build_operator_condition(institution_class.type, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.author.id":
            value = get_short_id_integer(value)
            join_condition = models.Affiliation.paper_id == work_class.paper_id
            filter_column = models.Affiliation.author_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.countries":
            value = get_short_id_text(value).upper()  # Country codes must be uppercase
            join_condition = models.AffiliationCountryDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationCountryDistinct.country_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.is_global_south":
            value = get_boolean_value(value)
            join_condition = models.Affiliation.paper_id == work_class.paper_id
            filter_column = models.Affiliation.is_global_south
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.ror":
            join_condition = and_(
                models.Work.paper_id == models.Affiliation.paper_id,
                models.Affiliation.affiliation_id == models.Institution.affiliation_id,
            )
            filter_condition = models.Institution.ror == value
            return and_(join_condition, filter_condition)

        elif key == "id":
            if isinstance(value, str):
                value = get_short_id_integer(value)
            elif isinstance(value, int):
                value = int(value)
            return build_operator_condition(model_column, operator, value)

        elif key == "authorships.author.orcid":
            join_condition = and_(
                models.Work.paper_id == models.Affiliation.paper_id,
                models.Affiliation.author_id == models.Author.author_id,
            )
            filter_condition = models.Author.orcid == value
            return and_(join_condition, filter_condition)

        elif key == "language":
            value = get_short_id_text(value).lower()
            return build_operator_condition(model_column, operator, value)

        elif key == "grants.funder":
            value = get_short_id_integer(value)
            join_condition = models.WorkFunder.paper_id == work_class.paper_id
            filter_column = models.WorkFunder.funder_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "sustainable_development_goals.id":
            value = get_short_id_integer(value)
            join_condition = models.WorkSdg.paper_id == work_class.paper_id
            filter_column = models.WorkSdg.sdg_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "authorships.institutions.continent":
            wiki_code = get_short_id_text(value)
            value = convert_wiki_to_continent_id(wiki_code)
            affiliation_continent_class = getattr(models, "AffiliationContinentDistinct")
            join_condition = models.AffiliationContinentDistinct.paper_id == work_class.paper_id
            filter_column = models.AffiliationContinentDistinct.continent_id
            filter_condition = build_operator_condition(filter_column, operator, value)
            return and_(join_condition, filter_condition)

        elif key == "related_to_text":
            r = requests.get(f"https://api.openalex.org/text/related-works?text={value}")
            if r.status_code == 200:
                results = r.json()
                related_paper_ids = [result["work_id"] for result in results]
                return work_class.paper_id.in_(related_paper_ids)
            else:
                raise ValueError(f"Failed to get related works for text: {value}")
       
        elif column_type in ["object", "array"] or is_object_entity:
            value = get_short_id_integer(value)
            return build_operator_condition(model_column, operator, value)

        elif column_type == "string":
            return build_operator_condition(model_column, operator, value)

        else:            
            return build_operator_condition(model_column, operator, value)

    def build_entity_filter_condition(self, filter):
        """ Returns a `condition` which represents `filter` for entities."""

        entity_class = get_entity_class(self.entity)

        key = filter.get("column_id")
        value = filter.get("value")
        operator = filter.get("operator") or "is"

        # ensure is valid filter
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

        if not redshift_column:
            raise(ValueError(f"Column {key} missing 'redshitFilterColumn' in entity config"))

        model_column = getattr(entity_class, redshift_column, None)

        print(f"Building entity filter: redshift_column: {redshift_column}, column_type: {column_type}, is_object_entity: {is_object_entity}, is_search_column: {is_search_column}, model_column: {model_column}")


        if column_type == "number":
            return build_number_condition(model_column, operator, value)

        elif column_type == "boolean":
            value = get_boolean_value(value)
            return build_operator_condition(model_column, operator, value)

        elif is_search_column:
            return model_column.ilike(f"%{value}%")

        elif key == "affiliations.institution.type":
            value = get_short_id_text(value).capitalize()
            return build_operator_condition(models.Institution.type, operator, value)
        
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

        elif key == "related_to_text" and self.entity == "authors":
            r = requests.get(f"https://api.openalex.org/text/related-authors?text={value}")
            if r.status_code == 200:
                results = r.json()
                related_author_ids = [result["author_id"] for result in results]
                return entity_class.author_id.in_(related_author_ids)
            else:
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

        elif key == "affiliations.institution.country_code" and self.entity == "authors":
            value = get_short_id_text(value).upper()
            affiliation_class = aliased(getattr(models, "Affiliation"))
            institution_class = aliased(getattr(models, "Institution"))
            join_condition = and_(
                affiliation_class.author_id == entity_class.author_id,
                institution_class.affiliation_id == affiliation_class.affiliation_id,
            )
            filter_condition = build_operator_condition(institution_class.country_code, operator, value)
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

        elif column_type == "string":
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

    def get_summary(self, query):
        if self.entity != "summary":
            return None

        summary_query = query.with_entities(
            func.count().label("count"),
            func.sum(models.Work.cited_by_count).label("sum(cited_by_count)"),
            func.sum(case([(models.Work.oa_status.in_(["gold", "hybrid", "green"]), 1)], else_=0)).label("sum(is_oa)"),
            func.avg(models.Work.fwci).label("mean(fwci)"),
            func.avg(models.Work.cited_by_count).label("mean(cited_by_count)")
        )

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

    def apply_sort(self, query, entity_class):
        if self.sort_by_column:
            sort_column = self.entity_config.get(self.sort_by_column).get(
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
        for column in self.show_columns:
            # count works
            if column == "count(works)" and self.entity in ["authors", "countries", "institutions"]:
                stat, related_entity = parse_stats_column(column)

                # use the existing join to calculate count_works
                affiliation_class = getattr(models, "Affiliation")

                # stat function
                stat_function = func.count(
                    func.distinct(affiliation_class.paper_id)
                )

                # group by
                query = query.group_by(*self.model_return_columns)

                # add stat column
                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )

                for filter in self.filter_aggs:
                    if filter.get("column_id") == "count(works)":
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "count(works)" and self.entity == "keywords":
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(
                    *self.model_return_columns + [entity_class.keyword_id]
                )

                stat_function = func.count(work_class.paper_id)

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )

                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "count(works)" and self.entity == "languages":
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(
                    *self.model_return_columns + [work_class.language]
                )

                stat_function = func.count(work_class.paper_id)

                query = query.add_columns(
                    work_class.language,
                    stat_function.label(f"{stat}({related_entity})")
                )
                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "count(works)" and self.entity in ["continents", "domains", "fields", "funders", "institution-types", "licenses", "publishers", "sdgs", "source-types", "subfields", "work-types"]:
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(
                    *self.model_return_columns
                )

                stat_function = func.count(func.distinct(work_class.paper_id))

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )
                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "count(works)" and self.entity == "sources":
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(
                    *self.model_return_columns + [entity_class.source_id]
                )

                stat_function = func.count(work_class.paper_id)

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )
                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "count(works)" and self.entity == "topics":
                stat, related_entity = parse_stats_column(column)

                work_topic_class = getattr(models, "WorkTopic")

                query = query.group_by(
                    *self.model_return_columns + [entity_class.topic_id]
                )

                query = query.filter(
                    work_topic_class.topic_rank == 1
                )  # only take the first topic

                stat_function = func.count(func.distinct(work_topic_class.paper_id))

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )
                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            # sum citations
            elif column == "sum(citations)" and self.entity in ["authors", "countries", "domains", "fields", "funders", "institutions", "keywords", "languages", "publishers", "subfields", "sdgs", "sources", "topics", "work-types"]:
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(*self.model_return_columns)

                stat_function = func.sum(work_class.cited_by_count)

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )

                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "mean(fwci)" and self.entity in ["authors", "countries", "domains", "fields", "funders", "institutions", "keywords", "languages", "publishers", "sdgs", "sources", "subfields", "topics", "work-types"]:
                work_class = getattr(models, "Work")

                stat_function = func.avg(work_class.fwci)

                query = query.add_columns(stat_function.label("mean_fwci"))

                query = query.group_by(*self.model_return_columns)

                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
            elif column == "percent(is_open_access)" and self.entity == "institutions":
                stat, related_entity = parse_stats_column(column)

                work_class = getattr(models, "Work")

                query = query.group_by(*self.model_return_columns)

                open_access_case = case(
                    [(work_class.oa_status.in_(["gold", "hybrid", "green"]), 1)],
                    else_=0
                )

                stat_function = (
                        func.sum(cast(open_access_case, Float)) / cast(func.count(work_class.paper_id),
                                                                       Float)
                )

                query = query.add_columns(
                    stat_function.label(f"{stat}({related_entity})")
                )
                for filter in self.filter_aggs:
                    if filter.get("column_id") == column:
                        query = self.filter_stats(
                            query, stat_function, filter["operator"], filter["value"]
                        )

                if self.sort_by_column == column:
                    query = self.sort_from_stat(
                        query, self.sort_by_order, stat_function
                    )
        return query

    @staticmethod
    def sort_from_stat(query, sort_by_order, sort_func):
        if sort_by_order:
            if sort_by_order == "desc":
                query = query.order_by(sort_func.desc().nulls_last())
            else:
                query = query.order_by(sort_func.asc().nulls_last())
        return query

    def sfilter_stats(self, query, stat_function, operator, value):
        """Apply filtering on the calculated stat."""
        if operator == "is greater than" or operator == ">":
            query = query.having(stat_function > int(value))
        elif operator == "is greater than or equal to" or operator == ">=":
            query = query.having(stat_function >= int(value))
        elif operator == "is less than" or operator == "<":
            query = query.having(stat_function < int(value))
        elif operator == "is less than or equal to" or operator == "<=":
            query = query.having(stat_function <= int(value))
        elif operator == "is":
            query = query.having(stat_function == int(value))
        elif operator == "is not" or operator == "!=":
            query = query.having(stat_function != int(value))
        return query

    def get_entity_config(self):
        entity_for_config = "works" if self.entity == "summary" else self.entity
        return all_entities_config.get(entity_for_config).get("columns")


def get_entity_class(entity):
    if entity == "countries":
        entity_class = getattr(models, "Country")
    elif entity == "institution-types":
        entity_class = getattr(models, "InstitutionType")
    elif entity == "source-types":
        entity_class = getattr(models, "SourceType")
    elif entity == "work-types":
        entity_class = getattr(models, "WorkType")
    elif entity == "summary":
        entity_class = getattr(models, "Work")
    else:
        entity_class = getattr(models, entity[:-1].capitalize())
    return entity_class


def build_operator_condition(column, operator, value):
    print("model_column / operator / value ")
    print(f"{column} / {operator} / {value}", flush=True)
    if operator == "is":
        return column == value
    elif operator == "is not":
        return column != value
    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_number_condition(column, operator, value):
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


def get_boolean_value(value):
    if isinstance(value, bool):
        return value
    elif value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False


def is_model_property(column, entity_class):
    attr = getattr(entity_class, column, None)

    # check if it's a standard Python property
    if isinstance(attr, property):
        return True

    if isinstance(attr, hybrid_property):
        return False  # do not skip, we want to add hybrid properties

    if hasattr(attr, "expression"):
        return False  # do not skip, this is likely a hybrid property

    return False


def get_short_id_text(value):
    value = value.split("/")[-1].lower()
    return value


def get_short_id_integer(value):
    value = get_short_id_text(value)
    value = re.sub(r"[a-zA-Z]", "", value)
    value = int(value)
    return value


def parse_stats_column(column):
    # use format like count(works) to get stat and entity
    print(column)
    stat = column.split("(")[0]
    entity = column.split("(")[1].split(")")[0]
    return stat, entity


def convert_wiki_to_continent_id(value):
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
