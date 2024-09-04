import re

from sqlalchemy import case, cast, desc, func, Float
from sqlalchemy.orm import aliased
from extensions import db

from combined_config import all_entities_config
from oql import models
from sqlalchemy.ext.hybrid import hybrid_property


class RedshiftQueryHandler:
    def __init__(
        self,
        entity,
        sort_by_column,
        sort_by_order,
        filters,
        return_columns,
        valid_columns,
    ):
        self.entity = entity
        self.sort_by_column = sort_by_column
        self.sort_by_order = sort_by_order
        self.filters = filters
        self.return_columns = return_columns
        self.valid_columns = valid_columns
        self.model_return_columns = []
        self.entity_config = all_entities_config.get(entity).get("columns")
        self.works_config = all_entities_config.get("works").get("columns")

    def execute(self):
        entity_class = get_entity_class(self.entity)  # from summarize_by

        query = self.build_joins(entity_class)
        query = self.set_columns(query, entity_class)
        query = self.apply_work_filters(query)
        query = self.apply_entity_filters(query, entity_class)
        query = self.apply_sort(query, entity_class)
        query = self.apply_stats(query, entity_class)

        count_query = db.session.query(func.count()).select_from(query.subquery())
        total_count = db.session.execute(count_query).scalar()

        results = query.limit(100).all()

        return total_count, results

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
        elif self.entity == "authors":
            query = (
                db.session.query(*columns_to_select)
                .distinct()
                .join(
                    models.Affiliation,
                    models.Affiliation.author_id == models.Author.author_id,
                )
                .join(models.Work, models.Work.paper_id == models.Affiliation.paper_id)
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
        else:
            query = db.session.query(*columns_to_select)

        self.model_return_columns = columns_to_select
        return query

    def set_columns(self, query, entity_class):
        columns_to_select = [entity_class]

        for column in self.return_columns:
            column_info = self.entity_config.get(column)
            if not column_info:
                continue

            redshift_column = column_info.get("redshiftDisplayColumn")
            if redshift_column.startswith("count("):
                # Handle aggregate columns elsewhere
                continue

            if is_model_property(redshift_column, entity_class):
                # Skip model properties
                continue

            if hasattr(entity_class, redshift_column):
                columns_to_select.append(getattr(entity_class, redshift_column))
        return query

    def apply_work_filters(self, query):
        if not self.filters:
            return query

        work_class = getattr(models, "Work")

        for filter in self.filters:
            subject_entity = filter.get("subjectEntity")
            key = filter.get("column_id")
            value = filter.get("value")
            operator = filter.get("operator")

            # ensure is valid filter
            if key is None or value is None or operator is None:
                continue

            # only filter by works
            if subject_entity != "works":
                continue

            # setup
            redshift_column = self.works_config.get(key).get("redshiftFilterColumn")
            column_type = self.works_config.get(key).get("type")
            is_object_entity = self.works_config.get(key).get("objectEntity")
            model_column = getattr(
                work_class, redshift_column, None
            )  # primary column to filter against

            # filters
            if column_type == "number":
                print(f"filtering by number {model_column}")
                query = self.filter_by_number(model_column, operator, query, value)
            elif column_type == "boolean":
                query = self.filter_by_boolean(model_column, query, value)
            elif ".search" in key:
                query = query.filter(model_column.ilike(f"%{value}%"))
            # specialized filters
            elif key == "keywords.id":
                value = get_short_id_text(value)
                work_keyword_class = aliased(getattr(models, "WorkKeyword"))
                query = query.join(
                    work_keyword_class,
                    work_keyword_class.paper_id == work_class.paper_id,
                )
                column = work_keyword_class.keyword_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "type" or key == "primary_location.source.type":
                value = get_short_id_text(value)
                query = self.do_operator_query(model_column, operator, query, value)
            elif key == "authorships.institutions.id":
                value = get_short_id_integer(value)
                affiliation_class = getattr(models, "AffiliationDistinct")
                query = query.join(
                    affiliation_class,
                    affiliation_class.paper_id == work_class.paper_id,
                )
                column = affiliation_class.affiliation_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "authorships.author.id":
                value = get_short_id_integer(value)
                affiliation_class = getattr(models, "Affiliation")
                query = query.join(
                    affiliation_class,
                    affiliation_class.paper_id == work_class.paper_id,
                )
                column = affiliation_class.author_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "authorships.countries":
                value = get_short_id_text(value)
                value = value.upper()  # country code needs to be uppercase
                affiliation_country_class = getattr(
                    models, "AffiliationCountryDistinct"
                )
                query = query.join(
                    affiliation_country_class,
                    affiliation_country_class.paper_id == work_class.paper_id,
                )
                column = affiliation_country_class.country_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "authorships.institutions.ror":
                query = query.join(
                    models.Affiliation,
                    models.Work.paper_id == models.Affiliation.paper_id
                ).join(
                    models.Institution,
                    models.Affiliation.affiliation_id == models.Institution.affiliation_id
                )
                query = query.filter(models.Institution.ror == value)
            elif key == "id":
                if isinstance(value, str):
                    value = get_short_id_integer(value)
                elif isinstance(value, int):
                    value = int(value)
                model_column = getattr(work_class, "paper_id", None)
                query = self.do_operator_query(model_column, operator, query, value)
            elif key == "authorships.author.orcid":
                query = query.join(
                    models.Affiliation,
                    models.Work.paper_id == models.Affiliation.paper_id
                ).join(
                    models.Author,
                    models.Affiliation.author_id == models.Author.author_id
                )
                query = query.filter(models.Author.orcid == value)
            # id filters
            elif (
                column_type == "object" or column_type == "array"
            ) and is_object_entity:
                value = get_short_id_integer(value)
                query = self.do_operator_query(model_column, operator, query, value)
            elif column_type == "string":
                query = self.do_operator_query(model_column, operator, query, value)
            # array of string filters
            else:
                print(f"filtering by string {model_column}")
                query = self.do_operator_query(model_column, operator, query, value)

        return query

    def apply_entity_filters(self, query, entity_class):
        if not self.filters:
            return query

        for filter in self.filters:
            subject_entity = filter.get("subjectEntity")
            key = filter.get("column_id")
            value = filter.get("value")
            operator = filter.get("operator")

            # ensure is valid filter
            if key is None or value is None or operator is None:
                continue

            # only filter by other entities
            if subject_entity == "works":
                continue

            # do not filter stats
            if key.startswith("count(") or key == "mean(fwci)":
                continue

            # setup
            redshift_column = self.entity_config.get(key).get("redshiftFilterColumn")
            column_type = self.entity_config.get(key).get("type")
            is_object_entity = self.entity_config.get(key).get("objectEntity")
            model_column = getattr(entity_class, redshift_column, None)

            # filters
            if column_type == "number":
                query = self.filter_by_number(model_column, operator, query, value)
            elif column_type == "boolean":
                query = self.filter_by_boolean(model_column, query, value)
            elif column_type == "string":
                query = self.do_operator_query(model_column, operator, query, value)
            elif column_type == "search":
                query = query.filter(model_column.ilike(f"%{value}%"))
            # specialized filters
            elif key == "affiliations.institution.country_code" and self.entity == "authors":
                value = get_short_id_text(value)
                value = value.upper()
                affiliation_class = aliased(getattr(models, "Affiliation"))
                institution_class = aliased(getattr(models, "Institution"))
                query = query.join(
                    affiliation_class,
                    affiliation_class.author_id == entity_class.author_id,
                ).join(
                    institution_class,
                    affiliation_class.affiliation_id == institution_class.affiliation_id,
                )
                query = self.do_operator_query(institution_class.country_code, operator, query, value)
            elif (
                column_type == "object" or column_type == "array"
            ) and is_object_entity:
                value = get_short_id_text(value)
                value = value.upper() if "country_code" in key else value
                query = self.do_operator_query(model_column, operator, query, value)
            # array of string filters
            else:
                query = self.do_operator_query(model_column, operator, query, value)
        return query

    @staticmethod
    def do_operator_query(column, operator, query, value):
        if operator == "is":
            query = query.filter(column == value)
        elif operator == "is not":
            query = query.filter(column != value)
        return query

    @staticmethod
    def filter_by_number(model_column, operator, query, value):
        if operator == "is greater than":
            query = query.filter(model_column > int(value))
        elif operator == "is less than":
            query = query.filter(model_column < int(value))
        elif operator == "is not":
            query = query.filter(model_column != int(value))
        else:
            query = query.filter(model_column == int(value))
        return query

    def filter_by_boolean(self, model_column, query, value):
        value = self.get_boolean_value(value)
        query = query.filter(model_column == value)
        return query

    @staticmethod
    def get_boolean_value(value):
        if isinstance(value, bool):
            return value
        elif value.lower() == "true":
            return True
        elif value.lower() == "false":
            return False

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
            else:
                query = self.default_sort(query, entity_class)
        else:
            query = self.default_sort(query, entity_class)

        return query

    def default_sort(self, query, entity_class):
        default_sort_column = (
            "cited_by_count" if self.entity == "works" else "display_name"
        )
        return query.order_by(desc(getattr(entity_class, default_sort_column, None)))

    def apply_stats(self, query, entity_class):
        if self.return_columns:
            for column in self.return_columns:
                if column == "count(works)" and (
                    self.entity == "authors" or self.entity == "institutions"
                ):
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

                    for filter in self.filters:
                        if filter["column_id"] == "count(works)":
                            query = self.filter_stats(
                                query, stat_function, filter["operator"], filter["value"]
                            )

                    if self.sort_by_column == column:
                        query = self.sort_from_stat(
                            query, self.sort_by_order, stat_function
                        )

                elif column == "mean(fwci)" and self.entity == "institutions":
                    # use the existing join to calculate mean_fwci
                    work_class = getattr(models, "Work")

                    stat_function = func.avg(work_class.fwci)

                    query = query.add_columns(stat_function.label("mean_fwci"))

                    query = query.group_by(*self.model_return_columns)

                    if self.sort_by_column == column:
                        query = self.sort_from_stat(
                            query, self.sort_by_order, stat_function
                        )

                elif column == "count(citations)" and self.entity == "institutions":
                    stat, related_entity = parse_stats_column(column)

                    work_class = getattr(models, "Work")

                    query = query.group_by(*self.model_return_columns)

                    stat_function = func.sum(work_class.cited_by_count)

                    query = query.add_columns(
                        stat_function.label(f"{stat}({related_entity})")
                    )

                    for filter in self.filters:
                        if filter["column_id"] == "count(citations)":
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
                        [(work_class.oa_status != "closed", 1)],
                        else_=0
                    )

                    stat_function = (
                            func.sum(cast(open_access_case, Float)) / cast(func.count(work_class.paper_id),
                                                                           Float)
                    )

                    query = query.add_columns(
                        stat_function.label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        query = self.sort_from_stat(
                            query, self.sort_by_order, stat_function
                        )
                elif column == "count(works)" and self.entity == "topics":
                    stat, related_entity = parse_stats_column(column)

                    work_topic_class = getattr(models, "WorkTopic")

                    query = query.outerjoin(
                        work_topic_class,
                        work_topic_class.topic_id == entity_class.topic_id,
                    )

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

                    if self.sort_by_column == column:
                        query = self.sort_from_stat(
                            query, self.sort_by_order, stat_function
                        )

                elif column == "count(works)" and self.entity == "keywords":
                    stat, related_entity = parse_stats_column(column)

                    work_keyword_class = getattr(models, "WorkKeyword")

                    query = query.outerjoin(
                        work_keyword_class,
                        work_keyword_class.keyword_id == entity_class.keyword_id,
                    )

                    query = query.group_by(
                        *self.model_return_columns + [entity_class.keyword_id]
                    )

                    stat_function = func.count(work_keyword_class.paper_id)

                    query = query.add_columns(
                        stat_function.label(f"{stat}({related_entity})")
                    )

                    if self.sort_by_column == column:
                        query = self.sort_from_stat(
                            query, self.sort_by_order, stat_function
                        )

                elif column == "count(works)" and self.entity == "countries":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")
                    institution_class = getattr(models, "Institution")

                    query = query.join(
                        institution_class,
                        affiliation_class.affiliation_id
                        == institution_class.affiliation_id,
                    )

                    query = query.group_by(
                        *self.model_return_columns + [institution_class.country_code]
                    )

                    stat_function = func.count(
                        func.distinct(affiliation_class.paper_id)
                    )

                    query = query.add_columns(
                        institution_class.country_code,
                        stat_function.label(f"{stat}({related_entity})"),
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

    def filter_stats(self, query, stat_function, operator, value):
        """Apply filtering on the calculated stat."""
        if operator == "is greater than":
            query = query.having(stat_function > int(value))
        elif operator == "is less than":
            query = query.having(stat_function < int(value))
        elif operator == "is":
            query = query.having(stat_function == int(value))
        elif operator == "is not":
            query = query.having(stat_function != int(value))
        return query


def get_entity_class(entity):
    if entity == "countries":
        entity_class = getattr(models, "Country")
    elif entity == "institution-types":
        entity_class = getattr(models, "InstitutionType")
    elif entity == "source-types":
        entity_class = getattr(models, "SourceType")
    elif entity == "work-types":
        entity_class = getattr(models, "WorkType")
    else:
        entity_class = getattr(models, entity[:-1].capitalize())
    return entity_class


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
    stat = column.split("(")[0]
    entity = column.split("(")[1].split(")")[0]
    return stat, entity
