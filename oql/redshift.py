import re

from sqlalchemy import desc, func
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
        self.config = all_entities_config.get(entity).get("columns")

    def execute(self):
        entity_class = self.get_entity_class()

        query = self.set_columns(entity_class)
        query = self.apply_sort(query, entity_class)
        query = self.apply_filters(query, entity_class)
        query = self.apply_stats(query, entity_class)
        return query.limit(100).all()

    def get_entity_class(self):
        if self.entity == "countries":
            entity_class = getattr(models, "Country")
        elif self.entity == "institution-types":
            entity_class = getattr(models, "InstitutionType")
        elif self.entity == "source-types":
            entity_class = getattr(models, "SourceType")
        elif self.entity == "work-types":
            entity_class = getattr(models, "WorkType")
        else:
            entity_class = getattr(models, self.entity[:-1].capitalize())
        return entity_class

    def set_columns(self, entity_class):
        columns_to_select = [entity_class]
        for column in self.return_columns:
            column = self.config.get(column).get("redshiftDisplayColumn")
            if column.startswith("count("):
                # set with stats function
                continue
            elif self.is_model_property(column, entity_class):
                print(f"column {column} is a model property")
                # continue if column is a model property
                continue
            else:
                columns_to_select.append(getattr(entity_class, column, None))
        self.model_return_columns = columns_to_select
        query = db.session.query(*columns_to_select)
        return query

    def is_model_property(self, column, entity_class):
        attr = getattr(entity_class, column, None)

        # check if it's a standard Python property
        if isinstance(attr, property):
            return True

        if isinstance(attr, hybrid_property):
            return False  # Do not skip, we want to add hybrid properties

        if hasattr(attr, "expression"):
            return False  # Do not skip, this is likely a hybrid property

        return False

    def apply_sort(self, query, entity_class):
        if self.sort_by_column:
            sort_column = self.config.get(self.sort_by_column).get(
                "redshiftDisplayColumn"
            )
            if self.sort_by_column == "count(works)":
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

    def apply_filters(self, query, entity_class):
        if not self.filters:
            return query

        for filter in self.filters:
            key = filter.get("column_id")
            value = filter.get("value")
            operator = filter.get("operator")

            # ensure is valid filter
            if key is None or value is None or operator is None:
                continue

            # setup
            redshift_column = self.config.get(key).get("redshiftFilterColumn")
            column_type = self.config.get(key).get("type")
            is_object_entity = self.config.get(key).get("objectEntity")
            model_column = getattr(
                entity_class, redshift_column, None
            )  # primary column to filter against

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
            elif key == "keywords.id":
                value = self.get_short_id_text(value)
                work_keyword_class = getattr(models, "WorkKeyword")
                query = query.join(
                    work_keyword_class,
                    work_keyword_class.paper_id == entity_class.paper_id,
                )
                column = work_keyword_class.keyword_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "type":
                value = self.get_short_id_text(value)
                query = self.do_operator_query(model_column, operator, query, value)
            elif key == "authorships.institutions.id":
                value = self.get_short_id_integer(value)
                affiliation_class = getattr(models, "AffiliationDistinct")
                query = query.join(
                    affiliation_class,
                    affiliation_class.paper_id == entity_class.paper_id,
                )
                column = affiliation_class.affiliation_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "authorships.author.id":
                value = self.get_short_id_integer(value)
                affiliation_class = getattr(models, "Affiliation")
                query = query.join(
                    affiliation_class,
                    affiliation_class.paper_id == entity_class.paper_id,
                )
                column = affiliation_class.author_id
                query = self.do_operator_query(column, operator, query, value)
            elif key == "authorships.countries":
                value = self.get_short_id_text(value)
                value = value.upper()  # country code needs to be uppercase
                affiliation_country_class = getattr(
                    models, "AffiliationCountryDistinct"
                )
                query = query.join(
                    affiliation_country_class,
                    affiliation_country_class.paper_id == entity_class.paper_id,
                )
                column = affiliation_country_class.country_id
                query = self.do_operator_query(column, operator, query, value)
            # id filters
            elif (
                column_type == "object" or column_type == "array"
            ) and is_object_entity:
                value = self.get_short_id_integer(value)
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

    def get_short_id_text(self, value):
        value = value.split("/")[-1].lower()
        return value

    def get_short_id_integer(self, value):
        value = self.get_short_id_text(value)
        value = re.sub(r"[a-zA-Z]", "", value)
        value = int(value)
        return value

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

    def apply_stats(self, query, entity_class):
        if self.return_columns:
            for column in self.return_columns:
                if column == "count(works)" and self.entity == "authors":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")

                    # join
                    query = query.outerjoin(
                        affiliation_class,
                        affiliation_class.author_id == entity_class.author_id,
                    )

                    # group by
                    query = query.group_by(*self.model_return_columns)

                    # add stat column
                    query = query.add_columns(
                        func.count(func.distinct(affiliation_class.paper_id)).label(
                            f"{stat}({related_entity})"
                        )
                    )

                    # sort here instead of in sort function
                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).asc()
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

                    query = query.add_columns(
                        func.count(func.distinct(work_topic_class.paper_id)).label(
                            f"{stat}({related_entity})"
                        )
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(work_topic_class.paper_id).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(work_topic_class.paper_id).asc()
                            )

                elif column == "count(works)" and self.entity == "institutions":
                    stat, related_entity = parse_stats_column(column)

                    affiliation_class = getattr(models, "Affiliation")

                    # join
                    query = query.outerjoin(
                        affiliation_class,
                        affiliation_class.affiliation_id == entity_class.affiliation_id,
                    )

                    # group by
                    query = query.group_by(
                        entity_class.id,
                        entity_class.affiliation_id,
                        entity_class.display_name,
                        entity_class.ror,
                        entity_class.country_code,
                        entity_class.type,
                        entity_class.citations,
                        entity_class.oa_paper_count,
                    )

                    # add columns
                    query = query.add_columns(
                        func.count(func.distinct(affiliation_class.paper_id)).label(
                            f"{stat}({related_entity})"
                        )
                    )

                    # sort here instead of in sort function
                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).asc()
                            )

                elif column == "count(works)" and self.entity == "sources":
                    stat, related_entity = parse_stats_column(column)

                    work_class = getattr(models, "Work")

                    query = query.outerjoin(
                        work_class, work_class.journal_id == entity_class.source_id
                    )

                    query = query.group_by(
                        *self.model_return_columns + [entity_class.source_id]
                    )

                    query = query.add_columns(
                        func.count(work_class.paper_id).label(
                            f"{stat}({related_entity})"
                        )
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(work_class.paper_id).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(work_class.paper_id).asc()
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

                    query = query.add_columns(
                        func.count(work_keyword_class.paper_id).label(
                            f"{stat}({related_entity})"
                        )
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(work_keyword_class.paper_id).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(work_keyword_class.paper_id).asc()
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

                    query = query.add_columns(
                        institution_class.country_code,
                        func.count(func.distinct(affiliation_class.paper_id)).label(
                            f"{stat}({related_entity})"
                        ),
                    )

                    if self.sort_by_column == column:
                        if self.sort_by_order == "desc":
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).desc()
                            )
                        else:
                            query = query.order_by(
                                func.count(
                                    func.distinct(affiliation_class.paper_id)
                                ).asc()
                            )
        return query


def parse_stats_column(column):
    # use format like count(works) to get stat and entity
    stat = column.split("(")[0]
    entity = column.split("(")[1].split(")")[0]
    return stat, entity
